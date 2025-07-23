import unittest

from trialsynth.base.models import Condition, Intervention, Trial, Edge, Node


class TestBaseModels(unittest.TestCase):

    def setUp(self):
        """Set up the test case."""
        self.condition = Condition(
            text="COVID-19",
            origin="test_origin",
            ns="mesh",
            id="D000086382",
            description="Coronavirus Disease 2019",
            source="test_source",
            labels=["disease"],
        )
        self.intervention = Intervention(
            text="mRNA vaccine",
            origin="test_origin",
            ns="ncit",
            id="C172787",
            description="A vaccine that uses messenger RNA to instruct cells to produce "
                        "pathogenic proteins.",
            source="test_source",
            labels=["vaccine"],
        )
        self.trial = Trial(
            ns="trial_prefix",
            id="000000001",
            labels=["test_label"],
        )

    def test_nodes(self):
        node = Node(source="test_source", ns="test_ns", ns_id="test_ns_id")
        assert node.source == "test_source"
        assert node.ns == "test_ns"
        assert node.ns_id == "test_ns_id"
        # Tests the curie property
        assert node.curie == "test_ns:test_ns_id"

        # Test empty node
        empty_node = Node(source="test_source")
        assert empty_node.source == "test_source"
        assert empty_node.ns is None
        assert empty_node.ns_id is None
        assert empty_node.curie == ""

        # Test curie assignment
        empty_node.curie = "test_ns:test_ns_id"
        assert empty_node.ns == "test_ns"
        assert empty_node.ns_id == "test_ns_id"
        assert empty_node.curie == "test_ns:test_ns_id"

        # Test invalid curie assignment
        with self.assertRaises(ValueError):
            empty_node.curie = "invalid_curie_format"

    def test_condition(self):
        self.assertEqual(self.condition.curie, "mesh:D000086382")
        self.assertEqual(set(self.condition.labels), {"disease", "condition"})

    def test_intervention(self):
        self.assertEqual(self.intervention.curie, "ncit:C172787")
        self.assertEqual(set(self.intervention.labels), {"vaccine", "intervention"})

    def test_trial_node(self):
        self.trial.entities = [
            self.intervention, self.condition, Node(source="test_source")
        ]
        self.assertEqual(len(self.trial.conditions), 1)
        self.assertEqual(self.trial.interventions[0].curie, self.intervention.curie)
        self.assertEqual(len(self.trial.interventions), 1)
        self.assertEqual(self.trial.conditions[0].curie, self.condition.curie)

    def test_edge(self):
        condition_edge = Edge(
            trial=self.trial,
            entity=self.condition,
            source="test_source",
        )
        self.assertEqual(condition_edge.trial.curie, self.trial.curie)
        self.assertEqual(condition_edge.entity.curie, self.condition.curie)
        self.assertEqual(condition_edge.rel_type, "has_condition")

        intervention_edge = Edge(
            trial=self.trial,
            entity=self.intervention,
            source="test_source",
        )
        self.assertEqual(intervention_edge.trial.curie, self.trial.curie)
        self.assertEqual(intervention_edge.entity.curie, self.intervention.curie)
        self.assertEqual(intervention_edge.rel_type, "has_intervention")
