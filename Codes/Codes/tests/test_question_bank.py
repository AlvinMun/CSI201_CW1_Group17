import json, tempfile, unittest, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))
from server import load_questions

class QuestionBankTests(unittest.TestCase):
    def setUp(self):
        self.sample = Path(__file__).parents[1] / 'questions.json'
    def test_valid_bank_loads(self):
        quizzes = load_questions(self.sample)
        expected_quizzes = json.loads(self.sample.read_text(encoding='utf-8'))['quizzes']
        self.assertGreaterEqual(len(quizzes), 2)
        self.assertEqual(
            [quiz['quiz_id'] for quiz in quizzes],
            [quiz['quiz_id'] for quiz in expected_quizzes],
        )
        self.assertTrue(all(len(q['questions']) >= 5 for q in quizzes))
    def test_wrong_schema_version_rejected(self):
        data=json.loads(self.sample.read_text(encoding='utf-8')); data['schema_version']=2
        with tempfile.NamedTemporaryFile('w',encoding='utf-8',delete=False) as f:
            json.dump(data,f); name=f.name
        try:
            with self.assertRaises(ValueError): load_questions(name)
        finally: Path(name).unlink()
    def test_empty_file_rejected(self):
        with tempfile.NamedTemporaryFile('wb',delete=False) as f: name=f.name
        try:
            with self.assertRaises(ValueError): load_questions(name)
        finally: Path(name).unlink()

    def test_nonprintable_characters_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            bank_path = Path(directory) / 'questions.json'
            for field in ('title', 'description', 'text'):
                for value in ('\x01', 'Visible text\u200b'):
                    with self.subTest(field=field, value=value):
                        data = json.loads(self.sample.read_text(encoding='utf-8'))
                        quiz = data['quizzes'][0]
                        target = quiz['questions'][0] if field == 'text' else quiz
                        target[field] = value
                        bank_path.write_text(json.dumps(data), encoding='utf-8')
                        with self.assertRaisesRegex(ValueError, field):
                            load_questions(bank_path)

    def test_printable_unicode_and_empty_description_accepted(self):
        data = json.loads(self.sample.read_text(encoding='utf-8'))
        quiz = data['quizzes'][0]
        quiz['title'] = 'Café 题库'
        quiz['description'] = ''
        quiz['questions'][0]['text'] = 'Quelle est la capitale du Pérou ?'
        with tempfile.TemporaryDirectory() as directory:
            bank_path = Path(directory) / 'questions.json'
            bank_path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
            self.assertEqual(load_questions(bank_path), data['quizzes'])

if __name__=='__main__': unittest.main()
