import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from agentwal.core import AgentWALEngine, DeterministicReplayEngine, GENESIS_HASH


class TestAgentWAL(unittest.TestCase):
    def setUp(self):
        self.wal = AgentWALEngine(db_path=':memory:')
        self.replay = DeterministicReplayEngine(self.wal)

    def test_wal_two_phase_commit_and_integrity(self):
        # 1. Phase 1: Log Intent before tool execution
        step1 = self.wal.log_intent(
            session_id='sess_fintech_001',
            intent_action='debit_account',
            input_payload={'account_id': 'acct_99', 'amount': 450.0},
        )
        self.assertGreater(step1, 0)

        # 2. Phase 2: Commit Output after successful tool execution
        record = self.wal.commit_execution(
            step_id=step1,
            output_payload={'status': 'SUCCESS', 'tx_id': 'tx_88192'},
            status='EXECUTED_SUCCESS'
        )
        self.assertEqual(record.status, 'EXECUTED_SUCCESS')
        self.assertNotEqual(record.signature_hash, GENESIS_HASH)

        # 3. Verify cryptographic chain
        valid, err = self.wal.verify_ledger_integrity()
        self.assertTrue(valid, f'WAL chain verification failed: {err}')

    def test_crash_recovery_for_uncommitted_steps(self):
        # Simulate an uncommitted intent (e.g. system crashed mid-execution)
        step_pending = self.wal.log_intent(
            session_id='sess_crash_test',
            intent_action='drop_partition',
            input_payload={'partition': 'p2026_08'},
        )
        pending_list = self.wal.recover_uncommitted_steps('sess_crash_test')
        self.assertEqual(len(pending_list), 1)
        self.assertEqual(pending_list[0]['step_id'], step_pending)
        self.assertEqual(pending_list[0]['action'], 'drop_partition')

    def test_deterministic_time_travel_replay(self):
        s_id = 'sess_replay_test'
        s1 = self.wal.log_intent(s_id, 'fetch_user', {'uid': 'u1'})
        self.wal.commit_execution(s1, {'name': 'Alice'})

        s2 = self.wal.log_intent(s_id, 'update_role', {'uid': 'u1', 'role': 'admin'})
        self.wal.commit_execution(s2, {'updated': True})

        # Replay without side effects
        replayed = self.replay.replay_session(s_id)
        self.assertEqual(len(replayed), 2)
        self.assertEqual(replayed[0]['action'], 'fetch_user')
        self.assertEqual(replayed[1]['action'], 'update_role')


if __name__ == '__main__':
    unittest.main()
