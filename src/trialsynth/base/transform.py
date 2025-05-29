from datetime import datetime
from typing import Iterable, Tuple

from .models import BioEntity, Edge, Node, Trial
from .util import join_list_to_str


class Transformer:

    def flatten_trial_data(
        self, trial: Trial
    ) -> Tuple:
        """Flattens trial data into a tuple of strings.

        Parameters
        ----------
        trial: Trial
            The trial to transform

        Returns
        -------
        transformed_data: Tuple
            A tuple of the transformed data. In order of title, type, design, conditions, interventions, genes,
            primary_outcome, secondary_outcome, secondary_ids, source, phases.

        """
        return (
            trial.curie,
            self.transform_title(trial),
            self.transform_labels(trial),
            self.transform_design(trial),
            self.transform_entities(trial.conditions),
            self.transform_entities(trial.interventions),
            self.transform_primary_outcome(trial),
            self.transform_secondary_outcome(trial),
            self.transform_secondary_ids(trial),
            trial.source,
            self.transform_phases(trial.phases),
            trial.start_date.year if trial.start_date else "",
            self.tranform_anticipated_date(trial),
            trial.overall_status,
            trial.why_stopped if trial.why_stopped else ""
        )

    @staticmethod
    def tranform_anticipated_date(trial: Trial) -> str:
        if trial.start_date_type is not None:
            if trial.start_date_type.lower() == "anticipated":
                return "true"
            else:
                return "false"
        else:
            return "false"

    @staticmethod
    def transform_secondary_ids(trial: Trial) -> str:
        """Transforms a list of secondary IDs into a string."""
        return join_list_to_str([id.curie for id in trial.secondary_ids])

    @staticmethod
    def transform_secondary_outcome(trial: Trial) -> str:
        """Transforms the secondary outcome of a trial into a string."""
        trial.secondary_outcomes = join_list_to_str(
            [
                f'Measure: {outcome.measure.strip() if outcome.measure else ""}, '
                f'Time Frame: {outcome.time_frame.strip() if outcome.time_frame else ""}'
                for outcome in trial.secondary_outcomes
            ]
        )
        return trial.secondary_outcomes

    @staticmethod
    def transform_primary_outcome(trial: Trial) -> str:
        """Transforms the primary outcome of a trial into a string."""
        trial.primary_outcomes = join_list_to_str(
            [
                f'Measure: {outcome.measure.strip() if outcome.measure else ""}, '
                f'Time Frame: {outcome.time_frame.strip() if outcome.time_frame else ""}'
                for outcome in trial.primary_outcomes
            ]
        )
        return trial.primary_outcomes

    @staticmethod
    def transform_entities(entities: Iterable[BioEntity]) -> str:
        transformed_entities = []
        for entity in entities:
            entity.ns = entity.ns.lower()
            transformed_entities.append(entity.curie)

        transformed_entities = set(transformed_entities)
        return join_list_to_str(transformed_entities)


    @staticmethod
    def transform_design(trial: Trial) -> str:
        """Transforms the design of a trial into a string."""
        if trial.design.fallback:
            return trial.design.fallback

        return (
            f'Purpose: {trial.design.purpose.strip() if trial.design.purpose else ""}; '
            f'Allocation: {trial.design.allocation.strip() if trial.design.allocation else ""};'
            f'Masking: {trial.design.masking.strip() if trial.design.masking else ""}; '
            f'Assignment: {trial.design.assignment.strip() if trial.design.assignment else ""}'
        )

    @staticmethod
    def transform_labels(node: Node) -> str:
        """Transforms the type of trial into a string."""
        return join_list_to_str(node.labels)

    @staticmethod
    def transform_phases(phases: Iterable[str]) -> str:
        """Transforms the phases of a trial into a string."""
        if not list(phases):
            return ""
        return join_list_to_str([phase.strip() for phase in phases if phase.strip()])

    @staticmethod
    def transform_title(trial: Trial) -> str:
        """Transforms the title of a trial into a string."""
        return trial.title.strip()

    def flatten_bioentity(
        self, entity: BioEntity
    ) -> Tuple[str, str, str, str]:
        """Flattens a BioEntity into a tuple of strings.

        Parameters
        ----------
        entity : BioEntity
            The BioEntity to flatten

        Returns
        -------
        Tuple[str, str, str, str]
            A tuple of the flattened BioEntity. In order of curie, term, source.
        """
        return (
            entity.curie,
            entity.grounded_term,
            self.transform_labels(entity),
            entity.source,
        )

    @staticmethod
    def flatten_edge(edge: Edge) -> Tuple[str, str, str, str, str]:
        """Flattens an Edge into a tuple of strings.

        Parameters
        ----------
        edge : Edge
            The Edge to flatten

        Returns
        -------
        Tuple[str, str, str, str, str]
            A tuple of the flattened Edge. In order of trial_curie, bio_ent_curie, rel_type, rel_type_curie, source.
        """
        return (
            edge.trial.curie,
            edge.entity.curie,
            edge.rel_type,
            edge.source,
        )
