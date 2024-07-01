from pydantic import BaseModel


class WHOTrial(BaseModel):
    """WHO Trial model

    Attributes
    ----------
    curie : str
        CURIE
    name : str
        Name of the trial
    study_type : str
        Type of study
    study_design : list
        Design of the study
    countries : list
        Countries where the study was conducted
    conditions : list
        Conditions of the study
    intervention : list
        Interventions of the study
    primary_outcome : str
        Primary outcome of the study
    secondary_outcome : str
        Secondary outcome of the study
    mappings : str
        Mappings of the study
    """
    curie: str
    name: str
    study_type: str
    study_design: list
    countries: list
    conditions: list
    intervention: list
    primary_outcome: str
    secondary_outcome: str
    mappings: str
