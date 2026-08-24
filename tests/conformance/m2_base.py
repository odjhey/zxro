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

    def test_m2_missing_objects_have_no_side_effects(self):
        missing_m2, missing_home = self.missing_m2_namespace()
        with self.assertRaises(self.not_found_error):
            missing_m2.inspect("job")
        self.assertFalse(missing_home.exists())

    def test_m2_inspect_is_read_only(self):
        turn = self.create_m2_turn("readonly")
        before_turn = self.turns.get(turn.id)
        before_work = self.work.get("job")
        first = self.m2.inspect("job")
        second = self.m2.inspect("job")
        self.assertEqual(first, second)
        self.assertEqual(self.turns.get(turn.id), before_turn)
        self.assertEqual(self.work.get("job"), before_work)

    def test_native_provenance_rejects_unbounded_or_unsafe_values(self):
        turn = self.create_m2_turn("grammar")
        for source in ("manual source", "acpx/agent", ".manual", "a" * 65):
            with self.subTest(source=source):
                with self.assertRaises(self.validation_error):
                    self.turns.bind(turn.id, native_session_id="native", native_session_source=source)

    def test_m2_artifact_metadata_corruption_fails_closed(self):
        turn = self.create_m2_turn("corruption")
        self.m1.settle(turn.id, "test", "completed", "done", b"evidence")
        restore = self.corrupt_m2_artifact_metadata(turn)
        try:
            with self.assertRaises(self.unsafe_error):
                self.m2.inspect("job")
        finally:
            restore()

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
