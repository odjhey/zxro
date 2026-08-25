import concurrent.futures


class M1ProviderConformance:
    """Reusable M1 semantics. Fixtures provide setup, fault, cost, and corruption hooks."""

    def create_turn(self, turns=None, work_id="job"):
        return (turns or self.turns).create(work_id, "pi", "crew", "/tmp")

    def publish_and_handle(self, count):
        for _ in range(count):
            _, event = self.m1.settle(self.create_turn().id, "test", "completed", "done", None)
            self.m1.handle(event.event_id)
            self.published += 1
        self.m1.ack("main", self.published)

    def test_settlement_idempotency_conflict_and_progressive_artifact(self):
        turn = self.create_turn()
        payload = b"private evidence"
        settled, event = self.m1.settle(turn.id, "test", "completed", "done", payload)
        repeated, same_event = self.m1.settle(turn.id, "retry", "completed", "done", None)
        self.assertEqual(repeated, settled)
        self.assertEqual(same_event, event)
        self.assertNotIn(payload.decode(), repr(event))
        self.assertEqual(len(event.artifact_refs), 1)
        self.assertEqual(self.m1.artifact_path(event.artifact_refs[0])["bytes"], len(payload))
        with self.assertRaises(self.conflict_error):
            self.m1.settle(turn.id, "test", "failed", "done", None)

    def test_structured_verdict_round_trip_and_retry_identity(self):
        turn = self.create_turn()
        settled, event = self.m1.settle(turn.id, "test", "completed", "waiting", None, "blocked", "operator input")
        repeated, same_event = self.m1.settle(turn.id, "retry", "completed", "waiting", None, "blocked", "operator input")
        self.assertEqual((settled.verdict, settled.needs), ("blocked", "operator input"))
        self.assertEqual((event.verdict, event.needs), ("blocked", "operator input"))
        self.assertEqual(repeated, settled)
        self.assertEqual(same_event, event)
        with self.assertRaises(self.conflict_error):
            self.m1.settle(turn.id, "test", "completed", "waiting", None, "blocked", "different input")
        with self.assertRaises(self.conflict_error):
            self.m1.settle(turn.id, "test", "completed", "waiting", None, "partial", None)
    def test_multiple_artifacts_freeze_at_settlement(self):
        turn = self.create_turn()
        first = self.m1.artifact_put(turn.id, "review", b"review")
        second = self.m1.artifact_put(turn.id, "test-log", b"tests")
        settled, event = self.m1.settle(turn.id, "test", "completed", "done", None)
        self.assertEqual(settled.artifact_refs, (first.ref, second.ref))
        self.assertEqual(event.artifact_refs, settled.artifact_refs)
        self.assertEqual(self.m1.artifact_path(first.ref)["bytes"], 6)
        with self.assertRaises(self.conflict_error):
            self.m1.artifact_put(turn.id, "late", b"late")


    def test_unread_ack_pending_and_out_of_order_idempotent_handle(self):
        events = [self.m1.settle(self.create_turn().id, "test", "completed", f"done {index}", None)[1] for index in range(1, 4)]
        self.assertEqual([event.generation for event in self.m1.unread("main")], [1, 2, 3])
        self.m1.ack("main", 3)
        self.m1.ack("main", 3)
        with self.assertRaises(self.conflict_error):
            self.m1.ack("main", 2)
        with self.assertRaises(self.conflict_error):
            self.m1.ack("main", 4)
        self.assertEqual(self.m1.unread("main"), [])
        self.assertEqual([event.event_id for event in self.m1.pending("main")], [event.event_id for event in events])
        handled = self.m1.handle(events[2].event_id)
        self.assertEqual(self.m1.handle(events[2].event_id), handled)
        self.m1.handle(events[0].event_id)
        self.assertEqual([event.event_id for event in self.m1.pending("main")], [events[1].event_id])
        self.work.close("job")
        self.assertEqual([event.event_id for event in self.m1.pending("main")], [events[1].event_id])

    def test_concurrent_settlement_has_stable_unique_generations(self):
        turns = [self.create_turn() for _ in range(12)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(lambda turn: self.m1.settle(turn.id, "test", "completed", "done", None), turns))
        events = self.m1.unread("main")
        self.assertEqual([event.generation for event in events], list(range(1, 13)))
        self.assertEqual(len({event.event_id for _, event in results}), 12)
        self.assertEqual({event.turn_id for event in events}, {turn.id for turn in turns})

    def test_crash_repair_preserves_identity_and_visibility(self):
        turn = self.create_turn()
        event_id = self.interrupt_after_terminal_commit(turn)
        self.m1.settle(turn.id, "test", "completed", "done", None)
        events = self.m1.unread("main")
        self.assertEqual([(event.event_id, event.generation) for event in events], [(event_id, 1)])
        self.assertEqual([event.event_id for event in self.m1.pending("main")], [event_id])

    def test_mismatched_cross_record_evidence_fails_closed(self):
        turn = self.create_turn()
        _, event = self.m1.settle(turn.id, "test", "completed", "done", b"evidence")
        restore = self.corrupt_artifact_relationship(turn, event)
        with self.assertRaises(self.unsafe_error):
            self.m1.unread("main")
        restore()
        for invalid_generation in (True, "1", 1.5):
            restore = self.corrupt_event_identity_lookup(event, invalid_generation)
            for operation in (
                lambda: self.m1.unread("main"),
                lambda: self.m1.pending("main"),
                lambda: self.m1.handle(event.event_id),
                lambda: self.m1.ack("main", event.generation),
            ):
                with self.assertRaises(self.unsafe_error):
                    operation()
            restore()

    def test_ack_api_rejects_non_integer_without_mutation(self):
        event = self.m1.settle(self.create_turn().id, "test", "completed", "done", None)[1]
        for invalid in (True, "1", 1.5):
            with self.assertRaises(self.validation_error):
                self.m1.ack("main", invalid)
        self.assertEqual([item.event_id for item in self.m1.unread("main")], [event.event_id])

    def test_ack_integrity_failure_does_not_advance(self):
        events = [self.m1.settle(self.create_turn().id, "test", "completed", "done", None)[1] for _ in range(3)]
        restore = self.remove_ack_generation(events[1])
        with self.assertRaises(self.unsafe_error):
            self.m1.ack("main", 3)
        restore()
        self.assertEqual([event.generation for event in self.m1.unread("main")], [1, 2, 3])

    def test_resumable_handle_uses_authoritative_handled_state(self):
        event = self.m1.settle(self.create_turn().id, "test", "completed", "done", None)[1]
        self.interrupt_handle_after_authoritative_commit(event)
        self.assertNotIn(event.event_id, [item.event_id for item in self.m1.pending("main")])
        first = self.m1.handle(event.event_id)
        self.assertEqual(self.m1.handle(event.event_id), first)
        self.assertNotIn(event.event_id, [item.event_id for item in self.m1.pending("main")])

    def test_namespace_isolation(self):
        other_m1, other_turns = self.new_namespace()
        first = self.m1.settle(self.create_turn().id, "test", "completed", "first", None)[1]
        second_turn = self.create_turn(other_turns)
        second = other_m1.settle(second_turn.id, "test", "completed", "second", None)[1]
        self.assertEqual(first.generation, 1)
        self.assertEqual(second.generation, 1)
        self.assertEqual([event.summary for event in self.m1.unread("main")], ["first"])
        self.assertEqual([event.summary for event in other_m1.unread("main")], ["second"])

    def test_missing_objects_fail_without_creation(self):
        missing = self.missing_namespace()
        with self.assertRaises(self.validation_error):
            missing.ack("main", True)
        with self.assertRaises(self.not_found_error):
            missing.unread("main")
        with self.assertRaises(self.not_found_error):
            missing.handle("evt-" + "0" * 32)
        self.assert_missing_namespace_uncreated()

    def test_missing_terminal_result_or_artifact_fails_closed(self):
        turn = self.create_turn()
        self.m1.settle(turn.id, "test", "completed", "done", b"evidence")
        restore_turn = self.remove_turn(turn.id)
        with self.assertRaisesRegex(self.unsafe_error, "missing turn"):
            self.m1.unread("main")
        restore_turn()
        self.remove_artifact(turn.id, "stdin")
        with self.assertRaisesRegex(self.unsafe_error, "missing artifact"):
            self.m1.pending("main")

    def test_marker_committed_crash_history_compacts_to_fixed_empty_pending_cost(self):
        for count in (5, 35):
            for _ in range(count):
                event = self.m1.settle(self.create_turn().id, "test", "completed", "done", None)[1]
                self.interrupt_handle_after_authoritative_commit(event)
            self.assertEqual(self.m1.pending("main"), [])
            first_empty_cost = self.operation_cost(lambda: self.m1.pending("main"))
            self.assertEqual(self.operation_cost(lambda: self.m1.pending("main")), first_empty_cost)
            if count == 5:
                baseline = first_empty_cost
            else:
                self.assertEqual(first_empty_cost, baseline)

    def test_empty_views_and_new_settlement_ignore_handled_history(self):
        self.publish_and_handle(5)
        small_unread = self.operation_cost(lambda: self.m1.unread("main"))
        small_pending = self.operation_cost(lambda: self.m1.pending("main"))
        self.publish_and_handle(35)
        self.assertEqual(self.operation_cost(lambda: self.m1.unread("main")), small_unread)
        self.assertEqual(self.operation_cost(lambda: self.m1.pending("main")), small_pending)
        turn = self.create_turn()
        self.assertLessEqual(self.operation_cost(lambda: self.m1.settle(turn.id, "test", "completed", "new", None)), self.settlement_cost_limit)
        self.assertEqual([event.turn_id for event in self.m1.unread("main")], [turn.id])
