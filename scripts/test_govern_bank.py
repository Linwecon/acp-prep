"""Regression checks for the actual batch governance input contract."""
import copy
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
import io
import urllib.error
import govern_bank as g

class GovernanceContracts(unittest.TestCase):
    def setUp(self):
        self.q={'qid':'1-0001','chapter':1,'type':0,'stem':'哪项符合要求？','options':[{'option_label':'A','option_text':'方式甲'},{'option_label':'B','option_text':'方式乙'}]}
        self.text='本章规定方式甲适用于当前场景而方式乙不适用。'
        self.sections={1:{'text':self.text},2:{'text':self.text}}
        self.r={'answer':['A'],'per_option':[{'label':'A','selected':True},{'label':'B','selected':False}], 'supported':True,'quote':self.text,'chapter':1,'classification':'own','quality':'ok'}

    def test_existing_and_model_multiselect_normalize_equally(self):
        self.assertEqual(g.norm(['C','A']),g.norm('A,C'))

    def test_full_option_contract_and_source_required(self):
        self.assertTrue(g.validate_result(copy.deepcopy(self.r),self.q,self.sections)['supported'])
        for change in ({'per_option':[]},{'quote':'原文完全没有这个结论但模型说正确'},{'answer':['B']},{'supported':'true'}):
            r={**copy.deepcopy(self.r),**change}
            self.assertFalse(g.validate_result(r,self.q,self.sections)['supported'])

    def test_claimed_own_with_other_chapter_is_misplaced(self):
        r={**copy.deepcopy(self.r),'chapter':2}
        self.assertEqual(g.validate_result(r,self.q,self.sections)['classification'],'misplaced')

    def test_partial_true_quote_does_not_validate_fabrication(self):
        self.assertFalse(g.exact(self.text+'不存在的结论',self.text))

    def test_all_separate_exact_quotes_allowed_but_approximate_not(self):
        source=self.text+'\n另一段原文说明其他条件的适用范围。'
        self.assertTrue(g.exact(self.text+'\n另一段原文说明其他条件的适用范围。',source))
        self.assertFalse(g.exact(self.text+'\n另一段原文说明所有条件都适用。',source))

    def test_addition_and_question_repair_are_reversible(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with patch.multiple(g.cc,JSON_PATH=root/'bank.json',JS_PATH=root/'bank.js',LEDGER_PATH=root/'curate'/'ledger.json',BACKUP_DIR=root/'backup'):
                q={**copy.deepcopy(self.q),'seq':'0001','answer':'A','analysis':'旧解析'}
                q.pop('qid')
                bank={'chapters':{'1':'测试章'},'questions_by_chapter':{'1':[q]}}
                g.cc.write_bank(bank,backup=False)
                g.cc.append_batch('add_questions','test',[{'qid':'1-0001','after':copy.deepcopy(q)}],batch_id='add')
                done,_=g.cc.rollback_batch('add',dry_run=False)
                self.assertEqual(done,1)
                self.assertEqual(len(g.cc.bank_questions(g.cc.load_bank())),0)
                q.update(deleted=False,answer='B',type=0,stem='新题干')
                g.cc.write_bank(bank,backup=False)
                g.cc.append_batch('answer_fix','test',[{'qid':'1-0001','before':{'answer':'A,B','type':1,'stem':'旧题干'},'after':{'answer':'B','type':0,'stem':'新题干'}}],batch_id='repair')
                done,_=g.cc.rollback_batch('repair',dry_run=False)
                restored=g.cc.load_bank()['questions_by_chapter']['1'][0]
                self.assertEqual(done,1)
                self.assertEqual((restored['answer'],restored['type'],restored['stem']),('A,B',1,'旧题干'))

    def test_account_failure_stops_subsequent_requests(self):
        g.qc.MODEL_HALTED.clear()
        self.addCleanup(g.qc.MODEL_HALTED.clear)
        error=urllib.error.HTTPError('https://unit.invalid',400,'Bad Request',{},io.BytesIO(b'{"error":{"type":"Arrearage"}}'))
        with patch.object(g.qc.urllib.request,'urlopen',side_effect=error) as call:
            cfg={'base_url':'https://unit.invalid','api_key':'test-placeholder'}
            for _ in range(2):
                with self.assertRaises(g.qc.ModelAccessError):
                    g.qc.chat(cfg,'test-model',[])
            self.assertEqual(call.call_count,1)

if __name__=='__main__': unittest.main()
