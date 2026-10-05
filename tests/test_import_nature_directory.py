import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from import_nature_directory import validate


class NatureBrowserTests(unittest.TestCase):
    def fixture(self):
        journal={'name':'Nature Machine Intelligence','short':'NMI','issns':['2522-5839'],
                 'collection':{'family':'nature','url':'https://www.nature.com/natmachintell/articles','max_pages':12}}
        page={'url':journal['collection']['url']+'?year=2026','retrieved_at':'2026-10-05T01:00:00Z',
              'page_title':'Articles in 2026 | Nature Machine Intelligence','issns':['2522-5839'],
              'all_types':True,'total':146,'last_page':8,
              'records':[{'title':f'Synthetic {i}','article_type':'Article','date':'2026-10-01',
                          'article_url':f'https://www.nature.com/articles/synthetic{i}'} for i in range(20)]}
        return journal,{'version':'nature-browser-bibliography-1','journal':'NMI','pages':[page]}

    def test_selected_bibliography_only_no_completeness_claim(self):
        j,b=self.fixture(); pages=validate(b,j,'2026-10-01')
        self.assertEqual(len(pages[0]['parsed']['records']),20)
        self.assertNotIn('complete',pages[0])

    def test_reject_wrong_identity_filters_incomplete_page_and_extra_material(self):
        changes=[('issns',['0000-0000']),('all_types',False),('total',145),('last_page',9),
                 ('page_title','Articles in 2026 | Other'),('retrieved_at','2026-10-05T01:00:00'),
                 ('url','https://www.nature.com/natmachintell/articles?year=2026&type=article'),
                 ('url','https://www.nature.com/natmachintell/articles?year=2026&page=2')]
        for key,value in changes:
            j,b=self.fixture(); b['pages'][0][key]=value
            # 145 still needs eight pages and has a full first page; it is valid.
            if key=='total': b['pages'][0]['records'].pop()
            with self.subTest(key=key,value=value),self.assertRaises(ValueError): validate(b,j,'2026-10-01')
        for field in ['abstract','html','body']:
            j,b=self.fixture(); b['pages'][0]['records'][0][field]='Forbidden'
            with self.subTest(field=field),self.assertRaises(ValueError): validate(b,j,'2026-10-01')

    def test_multiple_contiguous_pages(self):
        j,b=self.fixture(); p=copy.deepcopy(b['pages'][0]); p['url']+='&page=2&sort=PubDate'
        b['pages'].append(p)
        self.assertEqual(len(validate(b,j,'2026-10-01')),2)


if __name__=='__main__': unittest.main()
