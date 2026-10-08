"""Synthetic fixtures validate enumeration and date boundaries, not topic relevance."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from collect_candidates import DirectoryParser, collect_crossref, collect_official, crossref_date, digest, reconcile, EventLog, parse_aps, inventory_summary, supplement_crossref
from tempfile import TemporaryDirectory
import collect_candidates as collector


def item(doi='10.1234/synthetic', **extra):
    return dict({'DOI': doi, 'ISSN': ['2522-5839'], 'title': ['Synthetic title'],
                 'URL': 'https://www.nature.com/articles/synthetic',
                 'published-online': {'date-parts': [[2026, 9, 30]]}}, **extra)


class Client:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.attempts = []

    def get(self, url):
        self.attempts.append({'retrieved_at': 'synthetic time'})
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return json.dumps({'status': 'ok', 'message': response})


class CollectorTests(unittest.TestCase):
    def test_missing_identity_issn_preserves_unresolved_candidate(self):
        journal = {'short': 'NMI', 'issns': ['2522-5839'], 'collection': {'family': 'nature'}}
        url = 'https://www.nature.com/articles/synthetic'
        official = [{'records': [{'title': 'Synthetic title', 'date': '2026-09-30',
                                   'article_url': url}]}]
        with TemporaryDirectory() as tmp:
            log = EventLog(Path(tmp) / 'log.jsonl')
            log.add('publisher_identity', {'key': 'identity:' + url, 'metadata': {}, 'url': url})
            rows = reconcile({}, official, journal, '2026-09-01', '2026-09-30',
                             '2026-09-30', Client([]), log)
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]['doi'])
        self.assertEqual(rows[0]['issns'], [])
        self.assertFalse(rows[0]['identity_verified'])
        self.assertEqual(rows[0]['window_membership'], 'unresolved')
        self.assertIn('doi_identity_unconfirmed', rows[0]['issues'])

    def test_cli_window_override_is_frozen_without_global_change(self):
        record=item(**{'published-online':{'date-parts':[[2026,10,1]]}})
        response=json.dumps({'status':'ok','message':{'items':[record],'total-results':1}})
        directory=('<title>Articles in 2026 | Nature Machine Intelligence</title><span>2026 (2)</span>'
                   '<li class="app-article-list-row__item"><a class="c-card__link" href="/articles/synthetic">Synthetic title</a>'
                   '<span class="c-meta__type">Article</span><time datetime="2026-10-01"></time></li>'
                   '<li class="app-article-list-row__item"><a class="c-card__link" href="/articles/guard">Guard</a>'
                   '<span class="c-meta__type">Article</span><time datetime="2026-09-30"></time></li><footer>2522-5839</footer>')
        class OfflineClient:
            def __init__(self,**kwargs): self.attempts=[]
            def get(self,url):
                self.attempts.append({'retrieved_at':'synthetic time'})
                return response if 'api.crossref.org' in url else directory
        with TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'config').mkdir();(root/'docs').mkdir()
            (root/'docs/screening-protocol.md').write_text('Synthetic rules')
            config={'screening_protocol':'docs/screening-protocol.md','initial_trial':{'start':'2026-09-01','end':'2026-09-30'},
                    'journals':[{'short':'NMI','name':'Nature Machine Intelligence','issns':['2522-5839'],
                                 'collection':{'family':'nature','url':collector.DIRECTORY,'max_pages':12}}]}
            source=root/'config/sources.json';source.write_text(json.dumps(config),encoding='utf8')
            original=source.read_bytes();out=root/'reports/runs/trial'
            argv=['collect_candidates.py','--out',str(out),'--as-of','2026-10-05']
            with patch.object(collector,'ROOT',root),patch.object(collector,'Client',OfflineClient),patch.object(sys,'argv',argv+[
                    '--window-start','2026-10-01','--window-end','2026-10-05']):
                self.assertEqual(collector.main(),0)
            frozen=json.loads((out/'inputs/sources.json').read_text(encoding='utf8'))
            self.assertEqual(frozen['initial_trial']['start'],'2026-10-01')
            self.assertEqual(frozen['initial_trial']['end'],'2026-10-05')
            self.assertEqual(source.read_bytes(),original)
            with patch.object(sys,'argv',argv+['--resume','--window-start','2026-10-01','--window-end','2026-10-05']):
                with self.assertRaises(SystemExit):collector.main()
            self.assertEqual(source.read_bytes(),original)

    def test_http_429_stops_other_queries_and_channels(self):
        from urllib.error import HTTPError
        with TemporaryDirectory() as tmp:
            log = EventLog(Path(tmp)/'log.jsonl')
            client = collector.Client(log=log)
            with patch.object(collector, 'urlopen', side_effect=HTTPError('https://api.crossref.org',429,'Limited',{},None)) as request:
                _, queries = collect_crossref(client,'2026-09-01','2026-09-30',log=log)
                self.assertEqual(request.call_count,1)
                self.assertTrue(client.stopped)
                self.assertEqual(queries[1]['error'],'not_started_rate_limit')
                journal={'short':'NMI','collection':{'family':'nature','url':collector.DIRECTORY,'max_pages':2}}
                self.assertFalse(collect_official(client,journal,'2026-09-01','2026-09-30',log)['complete'])
                with self.assertRaises(collector.CollectionStopped):
                    client.get('https://www.nature.com')
                self.assertEqual(request.call_count,1)

    def test_new_aps_slugs_and_titles(self):
        for name,slug in [('Physical Review E','pre'),('Physical Review Research','prresearch')]:
            journal={'name':name,'collection':{'slug':slug}}
            text=(f'<head><title>{name} - Recent Articles</title></head>'
                  f'<p>1 - 1 of 1 Results</p><h2 class="title"><a href="/{slug}/abstract/10.1103/synthetic">Synthetic</a></h2>'
                  '<span>Published 1 September 2026</span></main>')
            self.assertEqual(parse_aps(text,journal,'recent')['records'][0]['date'],'2026-09-01')

    def test_fresh_nmi_run_does_not_require_pilot_files(self):
        record=item()
        response=json.dumps({'status':'ok','message':{'items':[record],'total-results':1}})
        directory=('<html><head><title>Articles in 2026 | Nature Machine Intelligence</title></head>'
                   '<body><span>2026 (2)</span>'
                   '<li class="app-article-list-row__item"><a class="c-card__link" href="/articles/synthetic">Synthetic title</a>'
                   '<span class="c-meta__type">Article</span><time datetime="2026-09-30"></time></li>'
                   '<li class="app-article-list-row__item"><a class="c-card__link" href="/articles/guard">Guard title</a>'
                   '<span class="c-meta__type">Article</span><time datetime="2026-08-31"></time></li>'
                   '<footer>2522-5839</footer></body></html>')
        class OfflineClient:
            def __init__(self,**kwargs): self.attempts=[]
            def get(self,url):
                self.attempts.append({'retrieved_at':'synthetic time'})
                return response if 'api.crossref.org' in url else directory
        with TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'config').mkdir(); (root/'docs').mkdir()
            (root/'docs/screening-protocol.md').write_text('Synthetic rules')
            config={'screening_protocol':'docs/screening-protocol.md','initial_trial':{'start':'2026-09-01','end':'2026-09-30'},'journals':[
                {'short':'NMI','name':'Nature Machine Intelligence','issns':['2522-5839'],
                 'collection':{'family':'nature','url':'https://www.nature.com/natmachintell/articles','max_pages':12}}, {'short':'Other','name':'Other Journal','issns':['0000-0002']}]}
            (root/'config/sources.json').write_text(json.dumps(config),encoding='utf8')
            out=root/'reports/runs/output'
            with patch.object(collector,'ROOT',root),patch.object(collector,'Client',OfflineClient),patch.object(sys,'argv',[
                    'collect_candidates.py','--out',str(out),'--as-of','2026-10-03','--journals','NMI']):
                self.assertEqual(collector.main(),0)
            result=json.loads((out/'candidates.json').read_text(encoding='utf8'))
            self.assertEqual(len(result['records']),1)
            self.assertEqual(result['records'][0]['doi'],record['DOI'])
            coverage=json.loads((out/'coverage.json').read_text(encoding='utf8'))
            self.assertTrue(coverage['selected_journal_inventory_complete'])
            self.assertEqual(coverage['pending_journals'],[])
            self.assertEqual(coverage['requested_journals'],['NMI'])
            self.assertEqual([j['short'] for j in json.loads((out/'inputs/sources.json').read_text())['journals']],['NMI'])
            self.assertIsNone(collector.cached_nmi_pilot(EventLog(out/'collection-log.jsonl'),config))

    def test_changed_year_counter_requires_identical_second_prefix(self):
        journal = {'short':'NMI','name':'Nature Machine Intelligence','issns':['2522-5839'],
                   'collection':{'family':'nature','url':'https://www.nature.com/natmachintell/articles','max_pages':3}}
        def page(total, suffix, day):
            return ('<html><head><title>Articles in 2026 | Nature Machine Intelligence</title></head>'
                    f'<body><span>2026 ({total})</span><li class="c-pagination__item" data-page="3"></li>'
                    f'<li class="app-article-list-row__item"><a class="c-card__link" href="/articles/{suffix}">{suffix}</a>'
                    f'<span class="c-meta__type">Article</span><time datetime="{day}"></time></li>'
                    '<footer>2522-5839</footer></body></html>')
        first=page(40,'a','2026-09-30'); guard=page(41,'b','2026-08-31')
        class Pages:
            def __init__(self,responses): self.responses=iter(responses); self.attempts=[]
            def get(self,url):
                self.attempts.append({'retrieved_at':'synthetic time'})
                return next(self.responses)
        for changed in [False,True]:
            with TemporaryDirectory() as tmp:
                check=page(41,'different','2026-08-31') if changed else guard
                result=collect_official(Pages([first,guard,first,check]),journal,'2026-09-01','2026-09-30',EventLog(Path(tmp)/'log.jsonl'))
                self.assertEqual(result['complete'],not changed)
                self.assertTrue(result['prefix_verification']['required'])
                if changed:
                    self.assertIn('changed between',result['error'])

    def test_failed_shorter_traversal_retains_previous_evidence(self):
        journal={'short':'NMI','name':'Nature Machine Intelligence','issns':['2522-5839'],
                 'collection':{'family':'nature','url':'https://www.nature.com/natmachintell/articles','max_pages':3}}
        with TemporaryDirectory() as tmp:
            log=EventLog(Path(tmp)/'log.jsonl')
            rows=[{'title':'Preserved','date':'2026-09-01','article_url':'https://www.nature.com/articles/a'}]
            log.add('official_result',{'key':'official:NMI:directory:0','result':{'records':rows}})
            log.add('directory_revision',{'key':'NMI','revision':1})
            result=collect_official(Client([OSError('offline')]),journal,'2026-09-01','2026-09-30',log)
            self.assertFalse(result['complete'])
            self.assertEqual(result['records'],rows)
            self.assertEqual(result['retained_records_from_sequence'],1)

    def test_unicode_line_separators_do_not_split_jsonl_events(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp)/'log.jsonl'
            log = EventLog(path)
            log.add('evidence',{'key':'k','title':'A\u2028B\u2029C'})
            self.assertEqual(EventLog(path).latest('evidence','k')['title'],'A\u2028B\u2029C')

    def test_title_conflict_does_not_change_doi_inventory(self):
        record = item()
        row = {'doi':record['DOI'],'title':'Different presentation','date':'2026-09-30','article_url':record['URL']}
        rows = self.merge({record['DOI']:[{'metadata':record,'metadata_sha256':digest(record)}]}, {'records':[row]})
        summary = inventory_summary(rows,True)
        self.assertTrue(summary['candidate_inventory_complete'])
        self.assertFalse(summary['metadata_reconciliation_complete'])
        self.assertIn('publisher_crossref_title_conflict',rows[0]['issues'])

    def test_in_month_date_conflict_vs_cross_month_membership(self):
        record = item()
        official = {'records':[{'doi':record['DOI'],'title':'Synthetic title','date':'2026-09-29','article_url':record['URL']}]}
        obs = {record['DOI']:[{'metadata':record,'metadata_sha256':digest(record)}]}
        self.assertEqual(self.merge(obs,official)[0]['window_membership'],'in_window')
        record['published-online']['date-parts']=[[2026,10,2]]
        self.assertEqual(self.merge(obs,official)[0]['window_membership'],'unresolved')

    def test_exact_doi_supplement_rejects_wrong_issn_and_abstract(self):
        journal = {'issns':['2522-5839']}
        official = [{'records':[{'doi':'10.1234/synthetic','date':'2026-09-30'}]}]
        for response in [item(ISSN=['0000-0000']),item(abstract='forbidden')]:
            with TemporaryDirectory() as tmp:
                records = {}
                log = EventLog(Path(tmp)/'log.jsonl')
                supplement_crossref(Client([{'total-results':1,'items':[response]}]),journal,records,official,'2026-09-01','2026-09-30',log)
                self.assertFalse(records)
                self.assertIsNone(log.latest('crossref_supplement','supplement:10.1234/synthetic')['metadata'])

    def merge(self, records, official):
        journal = {'short':'NMI','name':'Nature Machine Intelligence','issns':['2522-5839'],
                   'collection':{'family':'nature'}}
        with TemporaryDirectory() as tmp:
            return reconcile(records,[official],journal,'2026-09-01','2026-09-30','2026-10-03',
                             Client([]),EventLog(Path(tmp)/'log.jsonl'))

    def test_log_chain_rejects_modified_metadata(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp)/'log.jsonl'
            log = EventLog(path)
            log.add('evidence',{'key':'k','title':'original'})
            self.assertEqual(EventLog(path).latest('evidence','k')['title'],'original')
            path.write_text(path.read_text(encoding='utf8').replace('original','modified'),encoding='utf8')
            with self.assertRaises(ValueError):
                EventLog(path)

    def test_aps_parser_only_extracts_titles_and_explicit_dates(self):
        journal = {'name':'Physical Review Letters','collection':{'slug':'prl'}}
        text = ('<title>Physical Review Letters - Recent Articles</title>'
                '<p>1 - 1 of 1 Results</p><h2 class="title"><a href="/prl/abstract/10.1103/test">'
                'A <i>title</i></a></h2><span> - Published 30 September, 2026</span>'
                '<p>DO NOT STORE ABSTRACT</p></main>')
        parsed = parse_aps(text,journal,'recent')
        self.assertEqual(parsed['records'][0]['doi'],'10.1103/test')
        self.assertEqual(parsed['records'][0]['date'],'2026-09-30')
        self.assertNotIn('ABSTRACT',json.dumps(parsed))
        with self.assertRaises(ValueError):
            parse_aps(text.replace('1 - 1 of 1','1 - 2 of 2'),journal,'recent')
        with_svg = '<head><title>Physical Review Letters - Recent Articles</title></head>' + text[text.index('<p>'):] + '<svg><title>Icon</title></svg><h2 class="title">Log in</h2>'
        self.assertEqual(parse_aps(with_svg,journal,'recent')['records'],parsed['records'])

    def test_all_configured_issns_are_queried(self):
        response = {'items': [],'total-results':0}
        _,queries = collect_crossref(Client([response]*6),'2026-09-01','2026-09-30',
                                     journal={'short':'Synthetic','issns':['1111-1111','2222-2222']})
        self.assertEqual(len(queries),6)
        self.assertTrue(all(q['complete'] for q in queries))
        self.assertEqual({q['issn'] for q in queries},{'1111-1111','2222-2222'})

    def test_card_parser_ignores_description_and_handles_void_tags(self):
        parser = DirectoryParser(2026)
        parser.feed('<html><head><title>Articles in 2026 | Nature Machine Intelligence</title></head>'
                    '<body><span>2026 (1)</span><li class="app-article-list-row__item">'
                    '<img src="unused"><h3><a class="c-card__link" href="/articles/synthetic">'
                    'Synthetic <i>title</i></a></h3><p>DO NOT STORE DESCRIPTION</p>'
                    '<ul><li>Author</li></ul><span class="c-meta__type">Article</span>'
                    '<time datetime="2026-09-30">30 Sept</time></li>'
                    '<footer>2522-5839</footer></body></html>')
        result = parser.finish()
        self.assertEqual(result['total'], 1)
        self.assertEqual(result['records'][0]['title'], 'Synthetic title')
        self.assertNotIn('DESCRIPTION', json.dumps(result))

    def test_access_or_empty_page_is_not_complete_directory(self):
        parser = DirectoryParser(2026)
        parser.feed('<html><title>Access verification</title><body>Please wait</body></html>')
        with self.assertRaises(ValueError):
            parser.finish()

    def test_current_last_page_without_hyperlink_is_counted(self):
        parser = DirectoryParser(2026)
        parser.feed('<li class="c-pagination__item" data-page="7"><a class="c-pagination__link" '
                    'href="/natmachintell/articles?year=2026&page=7">7</a></li>'
                    '<li class="c-pagination__item" data-page="8">'
                    '<span class="c-pagination__link c-pagination__link--active">8</span></li>')
        self.assertEqual(max(parser.pages), 8)

    def test_preferred_incomplete_date_does_not_fall_back_to_print(self):
        record = item(**{'published-online': {'date-parts': [[2026, 9]]},
                         'published-print': {'date-parts': [[2026, 9, 30]]}})
        self.assertEqual(crossref_date(record), (None, 'published-online', 'incomplete_preferred_date'))

    def test_terminal_page_requires_reported_unique_count(self):
        response = {'items': [item()], 'total-results': 2, 'next-cursor': 'ignored'}
        _, queries = collect_crossref(Client([response]*3), '2026-09-01', '2026-09-30')
        self.assertTrue(all(not q['complete'] for q in queries))

    def test_repeated_cursor_and_page_budget_are_incomplete(self):
        response = {'items': [item()], 'total-results': 2, 'next-cursor': '*'}
        _, queries = collect_crossref(Client([response]*3), '2026-09-01', '2026-09-30', rows=1)
        self.assertTrue(all(not q['complete'] for q in queries))
        response['next-cursor'] = 'next'
        _, queries = collect_crossref(Client([response]*3), '2026-09-01', '2026-09-30', rows=1, max_pages=1)
        self.assertTrue(all(q['error'] == 'page_budget_exhausted' for q in queries))

    def test_no_unselected_abstract_is_retained(self):
        response = {'items': [item(abstract='synthetic forbidden text')], 'total-results': 1}
        records, queries = collect_crossref(Client([response]*3), '2026-09-01', '2026-09-30')
        self.assertFalse(records)
        self.assertTrue(all(not q['complete'] for q in queries))

    def test_date_conflict_and_missing_official_record_remain_unresolved(self):
        record = item()
        obs = {'metadata': record, 'metadata_sha256': 'synthetic hash'}
        official = {'records': [{'title': 'Synthetic title', 'article_type': 'Article',
                                'date': '2026-09-29', 'article_url': record['URL']}]}
        rows = self.merge({record['DOI']: [obs]}, official)
        self.assertEqual(rows[0]['window_status'], 'needs_check')
        self.assertIn('publisher_crossref_date_conflict', rows[0]['issues'])
        rows = self.merge({record['DOI']: [obs]}, {'records': []})
        self.assertIn('not_found_in_official_target_window', rows[0]['issues'])

    def test_window_uses_online_date_and_includes_endpoints(self):
        observations = {}
        official = {'records': []}
        for idx, day in enumerate([[2026, 9, 1], [2026, 9, 30], [2026, 8, 31]]):
            record = item(doi=f'10.1234/synthetic{idx}', **{'published-online': {'date-parts': [day]},
                           'published-print': {'date-parts': [[2026, 9, 30]]},
                           'URL': f'https://www.nature.com/articles/synthetic{idx}'})
            observations[record['DOI']] = [{'metadata': record, 'metadata_sha256': str(idx)}]
            if idx < 2:
                official['records'].append({'title': 'Synthetic title', 'article_type': 'Article',
                                           'date': '2026-09-01' if idx == 0 else '2026-09-30',
                                           'article_url': record['URL']})
        rows = self.merge(observations, official)
        self.assertEqual([row['window_status'] for row in rows], ['out_of_window','in_window','in_window'])


if __name__ == '__main__':
    unittest.main()
