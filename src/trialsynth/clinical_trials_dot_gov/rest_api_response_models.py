"""
Models for the unflattened response from the clinicaltrials.gov REST API.

See https://clinicaltrials.gov/data-api/about-api/study-data-structure
for more details on the structure of the response.
"""
from pydantic import BaseModel, Field
from datetime import datetime


class SecondaryID(BaseModel):

    id_type: str = Field(alias="type")
    secondary_id: str = Field(alias="id")


class IDModule(BaseModel):

    nct_id: str = Field(alias="nctId")
    brief_title: str = Field(alias="briefTitle")
    secondary_ids: list[SecondaryID] = Field(alias="secondaryIds", default=[])


class ConditionsModule(BaseModel):

    conditions: list[str] = Field(default=[])


class DateStruct(BaseModel):

    date: datetime = Field(default=None)
    date_type: str = Field(alias="type", default=None)


class StatusModule(BaseModel):

    start_date_struct: DateStruct = Field(
        alias="startDateStruct", default=DateStruct()
    )
    primary_completion_date_struct: DateStruct = Field(
        alias="primaryCompletionDateStruct",
        default=DateStruct(),
        description="The date that the final participant was examined or "
                    "received an intervention for the purposes of final "
                    "collection of data for the primary outcome"
    )
    # Also known as "Study Completion Date", see:
    # https://clinicaltrials.gov/policy/protocol-definitions#LastFollowUpDate
    completion_date_struct: DateStruct = Field(
        alias="completionDateStruct",
        default=DateStruct(),
        description="The date the final participant was examined or received "
                    "an intervention for purposes of final collection of data "
                    "for the primary and secondary outcome measures and "
                    "adverse events (for example, last participant’s last "
                    "visit)",
    )
    last_update_submit_date: datetime = Field(alias="lastUpdateSubmitDate", default=None)
    overall_status: str = Field(alias="overallStatus", default=None)
    why_stopped: str = Field(alias="whyStopped", default=None)


class DesignMaskingInfo(BaseModel):
    masking: str = Field(alias="masking", default=None)


class DesignInfo(BaseModel):
    purpose: str = Field(alias="primaryPurpose", default=None)
    allocation: str = Field(alias="allocation", default=None)
    masking_info: DesignMaskingInfo = Field(
        alias="maskingInfo", default=DesignMaskingInfo()
    )
    intervention_assignment: str = Field(alias="interventionModel", default=None)
    observation_assignment: str = Field(alias="observationalModel", default=None)


class DesignModule(BaseModel):

    study_type: str = Field(alias="studyType", default=None)
    design_info: DesignInfo = Field(alias="designInfo", default=DesignInfo())
    phases: list[str] = Field(alias="phases", default=[])


class Reference(BaseModel):
    # See: https://clinicaltrials.gov/policy/protocol-definitions#references

    pmid: str = Field(alias="pmid", default=None)  # Reference PMID
    type: str = Field(alias="type", default=None)  # One of BACKGROUND, RESULT, DERIVED
    citation: str = Field(alias="citation", default=None)


class ReferencesModule(BaseModel):

    references: list[Reference] = Field(alias="references", default=[])


class Intervention(BaseModel):

    name: str = Field(default=None)
    intervention_type: str = Field(alias="type")
    description: str = Field(default=None)


class ArmsInterventionsModule(BaseModel):

    arms_interventions: list[Intervention] = Field(alias="interventions", default=[])


class Mesh(BaseModel):

    term: str
    mesh_id: str = Field(alias="id")


class InterventionBrowseModule(BaseModel):

    intervention_meshes: list[Mesh] = Field(alias="meshes", default=[])


class ConditionBrowseModule(BaseModel):

    condition_meshes: list[Mesh] = Field(alias="meshes", default=[])


class Outcome(BaseModel):
    measure: str = Field(alias="measure", default=None)
    time_frame: str = Field(alias="timeframe", default=None)


class OutcomesModule(BaseModel):
    primary_outcome: list[Outcome] = Field(alias="primaryOutcomes", default=[])
    secondary_outcome: list[Outcome] = Field(alias="secondaryOutcomes", default=[])


class DescriptionModule(BaseModel):

    brief_summary: str = Field(alias="briefSummary", default=None)
    detailed_description: str = Field(alias="detailedDescription", default=None)


class ProtocolSection(BaseModel):

    id_module: IDModule = Field(alias="identificationModule")
    conditions_module: ConditionsModule = Field(
        alias="conditionsModule", default=ConditionsModule()
    )
    description_module: BaseModel = Field(
        alias="descriptionModule", default=DescriptionModule()
    )
    design_module: DesignModule = Field(alias="designModule", default=DesignModule())
    arms_interventions_module: ArmsInterventionsModule = Field(
        alias="armsInterventionsModule", default=ArmsInterventionsModule()
    )
    outcomes_module: OutcomesModule = Field(
        alias="outcomesModule", default=OutcomesModule()
    )
    status_module: StatusModule = Field(
        alias="statusModule", default=StatusModule()
    )
    references_module: ReferencesModule = Field(
        alias="referencesModule", default=ReferencesModule()
    )


class DerivedSection(BaseModel):

    condition_browse_module: ConditionBrowseModule = Field(
        alias="conditionBrowseModule", default=ConditionBrowseModule()
    )
    intervention_browse_module: InterventionBrowseModule = Field(
        alias="interventionBrowseModule", default=InterventionBrowseModule()
    )


class UnflattenedTrial(BaseModel):
    """
    Clinicaltrials.gov trial data from REST API response
    """

    protocol_section: ProtocolSection = Field(alias="protocolSection")
    derived_section: DerivedSection = Field(alias="derivedSection")
