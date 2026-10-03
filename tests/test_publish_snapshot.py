"""Reject corrupted or untraceable author metadata before public export."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from publish_snapshot import author_record
from screen_candidates import digest

class AuthorMetadataTests(unittest.TestCase):
    def setUp(self):
        self.record = {'doi':'10.1/test', 'title':'Test', 'issns':['0000-0001']}
        self.row = {'doi':'10.1/test', 'record_sha256':digest(self.record),
                    'authors':['Ada Example'], 'status':'available',
                    'basis':'Matched source', 'retrieved_at':'2026-10-03T00:00:00Z',
                    'source_url':'https://example.org/authors', 'attempts':[]}
        self.rehash(self.row)

    def rehash(self, row):
        row['metadata_sha256']=digest({k:v for k,v in row.items() if k not in {'attempts','metadata_sha256'}})

    def test_valid_and_unresolved(self):
        self.assertEqual(author_record(self.row,self.record)['authors'],['Ada Example'])
        row=deepcopy(self.row);row.update(authors=[],status='unresolved');self.rehash(row)
        self.assertEqual(author_record(row,self.record)['status'],'unresolved')

    def test_record_and_content_mismatch(self):
        for key,value in [('record_sha256','wrong'),('doi','10.1/wrong'),('authors',['Altered'])]:
            row=deepcopy(self.row);row[key]=value
            if key!='authors':self.rehash(row)
            with self.subTest(key=key),self.assertRaises(ValueError):author_record(row,self.record)

    def test_placeholder_and_missing_source_rejected(self):
        for change in [{'authors':['Anonymous']},{'authors':[]},{'source_url':'javascript:alert(1)'},{'retrieved_at':''},{'status':'unresolved'}]:
            row=deepcopy(self.row);row.update(change);self.rehash(row)
            with self.subTest(change=change),self.assertRaises(ValueError):author_record(row,self.record)
