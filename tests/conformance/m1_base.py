class M1ProviderConformance:
    """Reusable M1 semantics. Provider fixtures supply setup and fault hooks."""

    def publish_and_handle(self, count):
        for _ in range(count):
            turn = self.turns.create("job", "pi", "crew", "/tmp")
            _, event = self.m1.settle(turn.id, "test", "completed", "done", None)
            self.m1.handle(event.event_id)
            self.published += 1
        self.m1.ack("main", self.published)

    def test_missing_terminal_result_or_artifact_fails_closed(self):
        turn = self.turns.create("job", "pi", "crew", "/tmp")
        self.m1.settle(turn.id, "test", "completed", "done", b"evidence")
        restore_turn = self.remove_turn(turn.id)
        with self.assertRaisesRegex(self.unsafe_error, "missing turn"):
            self.m1.unread("main")
        restore_turn()
        self.remove_artifact(turn.id, "stdin")
        with self.assertRaisesRegex(self.unsafe_error, "missing artifact"):
            self.m1.pending("main")

    def test_empty_views_and_new_settlement_ignore_handled_history(self):
        self.publish_and_handle(5)
        small_unread = self.operation_cost(lambda: self.m1.unread("main"))
        small_pending = self.operation_cost(lambda: self.m1.pending("main"))
        self.publish_and_handle(35)
        self.assertEqual(self.operation_cost(lambda: self.m1.unread("main")), small_unread)
        self.assertEqual(self.operation_cost(lambda: self.m1.pending("main")), small_pending)
        turn = self.turns.create("job", "pi", "crew", "/tmp")
        self.assertLessEqual(self.operation_cost(lambda: self.m1.settle(turn.id, "test", "completed", "new", None)), self.settlement_cost_limit)
        self.assertEqual([event.turn_id for event in self.m1.unread("main")], [turn.id])
