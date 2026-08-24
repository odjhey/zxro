class M2ProviderConformance:
    """Provider-neutral M2 semantics shared by built-in and future providers."""

    def create_m2_turn(self, session="m2"):
        return self.turns.create("job", "pi", session, "/tmp")

    def test_native_binding_is_immutable_and_staged(self):
        turn = self.create_m2_turn()
        bound = self.turns.bind(turn.id, native_session_id="native-1")
        self.assertEqual(bound.native_session_id, "native-1")
        self.assertIsNone(bound.native_session_source)
        enriched = self.turns.bind(turn.id, native_session_source="acpx.agentSessionId")
        self.assertEqual(enriched.native_session_source, "acpx.agentSessionId")
        self.assertEqual(self.turns.bind(turn.id, "native-1", "acpx.agentSessionId"), enriched)
        with self.assertRaises(self.conflict_error):
            self.turns.bind(turn.id, native_session_id="native-2")
        with self.assertRaises(self.conflict_error):
            self.turns.bind(turn.id, native_session_source="manual")

    def test_inspect_returns_bounded_work_metadata(self):
        turn = self.create_m2_turn("inspect")
        payload = b"provider-neutral evidence"
        self.m1.settle(turn.id, "test", "completed", "done", payload)
        summary = self.m2.inspect("job")
        self.assertEqual(summary["work"], {"id": "job", "watchtower_id": "main", "state": "open"})
        item = next(item for item in summary["turns"] if item["id"] == turn.id)
        self.assertEqual(item["artifact_count"], 1)
        self.assertEqual(item["artifact_bytes"], len(payload))
        self.assertNotIn(payload.decode(), repr(summary))
        self.assertEqual(summary["inbox"]["unread_count"], 1)
        self.assertEqual(summary["inbox"]["pending_attention_count"], 1)
