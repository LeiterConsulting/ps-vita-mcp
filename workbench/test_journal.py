"""Local report-sharing failures cannot cause a device mutation replay."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from workbench.runner import Journal

class JournalTests(unittest.TestCase):
    def test_transient_sharing_error_commits_one_intent_and_one_mutation(self):
        with tempfile.TemporaryDirectory() as folder:
            j = Journal(Path(folder), 'fixture'); calls = []
            import os
            actual = os.replace; replacements = []
            def replace(a, b):
                replacements.append((a, b))
                if len(replacements) <= 2: raise PermissionError('simulated reader sharing lock')
                actual(a, b)
            with patch('workbench.runner.os.replace', side_effect=replace), patch('workbench.runner.time.sleep'):
                j.mutation('fixture', {}, lambda: calls.append('sent') or {'accepted': True})
            self.assertEqual(calls, ['sent'])
            report = json.loads((j.folder / 'report.json').read_text())
            self.assertEqual([e['kind'] for e in report['events']], ['mutation_intent', 'mutation_receipt'])

    def test_persistent_intent_commit_failure_never_submits_mutation(self):
        with tempfile.TemporaryDirectory() as folder:
            j = Journal(Path(folder), 'fixture'); calls = []
            with patch('workbench.runner.os.replace', side_effect=PermissionError('simulated persistent lock')) as replace, patch('workbench.runner.time.sleep'):
                with self.assertRaises(PermissionError): j.mutation('fixture', {}, lambda: calls.append('sent'))
            self.assertEqual(replace.call_count, 8)
            self.assertEqual(calls, [])

    def test_receipt_commit_failure_does_not_resubmit_completed_mutation(self):
        with tempfile.TemporaryDirectory() as folder:
            j = Journal(Path(folder), 'fixture'); calls = []
            import os
            actual = os.replace; count = 0
            def replace(a, b):
                nonlocal count
                count += 1
                if count > 1: raise PermissionError('simulated receipt commit lock')
                actual(a, b)
            with patch('workbench.runner.os.replace', side_effect=replace), patch('workbench.runner.time.sleep'):
                with self.assertRaises(PermissionError): j.mutation('fixture', {}, lambda: calls.append('sent') or {'accepted': True})
            self.assertEqual(calls, ['sent'])
            events = [json.loads(l) for l in (j.folder / 'journal.jsonl').read_text().splitlines()]
            self.assertEqual([e['kind'] for e in events], ['mutation_intent', 'mutation_receipt'])

if __name__ == '__main__': unittest.main(verbosity=2)
