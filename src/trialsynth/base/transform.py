from typing import Iterable, Tuple

from .models import BioEntity, Edge, Node, Trial


class Transformer:

    def flatten_trial_data(
        self, trial: Trial
    ) -> Tuple[str, str, str, str, str, str, str, str, str, str]:
        """Flattens trial data into a tuple of strings.

        Parameters
        ----------
        trial: Trial
            The trial to transform

        Returns
        -------
        transformed_data: Tuple
            A tuple of the transformed data. In order of title, type, design, conditions, interventions,
            primary_outcome, secondary_outcome, secondary_ids.

        """
        return (
            trial.curie,
            self.transform_title(trial),
            self.transform_labels(trial),
            self.transform_design(trial),
            self.transform_conditions(trial),
            self.transform_interventions(trial),
            self.transform_primary_outcome(trial),
            self.transform_secondary_outcome(trial),
            self.transform_secondary_ids(trial),
            trial.source,
        )

    @staticmethod
    def transform_secondary_ids(trial: Trial) -> str:
        """Transforms a list of secondary IDs into a string."""
        return ";".join([id.curie for id in trial.secondary_ids])

    @staticmethod
    def transform_secondary_outcome(trial: Trial) -> str:
        """Transforms the secondary outcome of a trial into a string."""
        trial.secondary_outcomes = ";".join(
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
        trial.primary_outcomes = ";".join(
            [
                f'Measure: {outcome.measure.strip() if outcome.measure else ""}, '
                f'Time Frame: {outcome.time_frame.strip() if outcome.time_frame else ""}'
                for outcome in trial.primary_outcomes
            ]
        )
        return trial.primary_outcomes

    @staticmethod
    def _transform_entities(entities: Iterable[BioEntity]) -> str:
        transformed_entities = []
        for entity in entities:
            entity.ns = entity.ns.lower()
            transformed_entities.append(entity.curie)
        return ";".join(transformed_entities)

    def transform_interventions(self, trial: Trial) -> str:
        """Transforms a list of interventions into a string."""
        return self._transform_entities(set(trial.interventions))

    def transform_conditions(self, trial: Trial) -> str:
        """Transforms a list of conditions into a string."""
        return self._transform_entities(set(trial.conditions))

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
        return ";".join([label for label in node.labels])

    @staticmethod
    def transform_title(trial: Trial) -> str:
        """Transforms the title of a trial into a string."""
        return trial.title.strip()

    def flatten_bioentity(self, entity: BioEntity) -> Tuple[str, str, str, str]:
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
        return entity.curie, entity.term, self.transform_labels(entity), entity.source

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
            edge.trial_curie,
            edge.bio_ent_curie,
            edge.rel_type,
            edge.rel_type_curie,
            edge.source,
        )
