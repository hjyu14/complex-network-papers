"""Synthetic minimal bibliographic observations, never stored publisher HTML."""
import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from import_aip_directory import normalize


class AIPTests(unittest.TestCase):
    def fixture(self):
        journal={'name':'Chaos: An Interdisciplinary Journal of Nonlinear Science','short':'Chaos',
                 'issns':['1089-7682','1054-1500'],'collection':{'max_pages':12,'article_lookups':120}}
        stamp='2026-10-04T01:00:00Z'
        rows=[]; articles=[]
        for i in range(20):
            month,day=('September','30') if i<19 else ('August','31')
            doi=f'10.1063/synthetic{i}'
            url=f'https://pubs.aip.org/aip/cha/article/synthetic{i}'
            rows.append({'doi':doi,'title':f'Synthetic {i}','article_url':url,'month':f'Published: {month} 2026'})
            articles.append({'doi':doi,'title':f'Synthetic {i}','journal':journal['name'],'issn':'1054-1500',
                             'date_text':f'{month} {day} 2026','citation_date':'2026/09/01','url':url,'retrieved_at':stamp})
        bundle={'version':'aip-browser-bibliography-1','journal':'Chaos','window_start':'2026-09-01','window_end':'2026-09-30',
                'pages':[{'url':'https://pubs.aip.org/aip/cha/search-results?q=*&sort=Date+-+Newest+First&page=1',
                          'sort':'Date - Newest First','retrieved_at':stamp,'records':rows}],
                'issues':[{'url':'https://pubs.aip.org/aip/cha/issue/36/9','month':'2026-09',
                           'dois':[r['doi'] for r in rows[:19]],'retrieved_at':stamp}], 'articles':articles}
        return journal,bundle

    def parse(self,j,b):
        return normalize(b,j,'2026-09-01','2026-09-30')

    def test_explicit_day_not_issue_month_metadata(self):
        j,b=self.fixture(); result=self.parse(j,b)
        self.assertTrue(result['complete'])
        self.assertEqual(result['records'][0]['date'],'2026-09-30')
        self.assertEqual(result['records'][0]['publisher_date_observation']['citation_date'],'2026/09/01')

    def test_no_date_fallback_for_missing_article_observation(self):
        j,b=self.fixture(); b['articles'].pop()
        with self.assertRaises(ValueError): self.parse(j,b)

    def test_issue_difference_and_duplicate_rejected(self):
        for mode in ['issue','duplicate','order','filter','page']:
            j,b=self.fixture()
            if mode=='issue': b['issues'][0]['dois'].pop()
            if mode=='duplicate': b['pages'][0]['records'][1]=copy.deepcopy(b['pages'][0]['records'][0])
            if mode=='order': b['articles'][0]['date_text']='September 01 2026'
            if mode=='filter': b['pages'][0]['url']+='&f_Subjects=Networks'
            if mode=='page': b['pages'][0]['url']=b['pages'][0]['url'].replace('page=1','page=2')
            with self.subTest(mode=mode),self.assertRaises(ValueError): self.parse(j,b)

    def test_abstract_wrong_issn_and_incomplete_date_rejected(self):
        for field,value in [('abstract','Forbidden'),('issn','0000-0000'),('date_text','September 2026')]:
            j,b=self.fixture(); b['articles'][0][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError): self.parse(j,b)

    def test_title_difference_preserved(self):
        j,b=self.fixture(); b['articles'][0]['title']='Changed title'
        self.assertTrue(self.parse(j,b)['records'][0]['title_identity_conflict'])


if __name__=='__main__': unittest.main()
