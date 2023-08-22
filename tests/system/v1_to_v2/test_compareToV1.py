import pandas as pd
import numpy as np
from csodiaq.identification import Identifier
from csodiaq.scoring import (
    create_peptide_fdr_output_from_full_output,
    create_protein_fdr_output_from_peptide_fdr_output,
    create_spectral_fdr_output_from_full_output,
)
from csodiaq.targetedReanalysis import (
    create_mass_spec_input_dataframes_for_targeted_reanalysis_of_identified_peptides,
)
from csodiaq.loaders.query import QueryLoaderContext
import os
import pickle
import pytest


def get_parent_dir():
    return os.path.dirname(os.path.abspath(__file__))


def get_file_from_system_test_folder(file):
    return os.path.join(get_parent_dir(), "test_files", file)


@pytest.fixture
def commandLineArgs():
    args = {
        "command": "id",
        "input": [get_file_from_system_test_folder("20190412_DI2A_1to1_tMS2_n3.mzXML")],
        "library": get_file_from_system_test_folder("system_test_library.csv"),
        "output": "",
        "matchTolerance": 30,
        "noCorrection": False,
        "correctionDegree": 0,
        "histogram": False,
    }
    return args


def assert_numeric_pandas_dataframes_are_equal(expectedDf, df, type):
    columns = get_columns_that_should_match(type)
    expectedDf = expectedDf[columns].sort_values(columns)
    df = df[columns].sort_values(columns)
    for columnName in columns:
        expectedColumn = np.array(expectedDf[columnName])
        column = np.array(df[columnName])
        if expectedColumn.dtype.kind in np.typecodes["AllFloat"]:
            np.testing.assert_array_almost_equal(expectedColumn, column)
        else:
            np.testing.assert_array_equal(expectedColumn, column)


def get_columns_that_should_match(type):
    if type == "match":
        return [
            "libraryIntensity",
            "queryIntensity",
            "ppmDifference",
        ]
    elif type == "score":
        return [
            "cosineScore",
            "maccScore",
        ]
    elif type == "full":
        return ["scan", "peptide", "cosine"]
    elif type == "spectral":
        return [
            "scan",
            "peptide",
            "cosine",
            "spectralFDR",
        ]
    elif type == "peptide":
        return [
            "scan",
            "peptide",
            "cosine",
            "peptideFDR",
        ]
    elif type == "protein":
        return [
            "scan",
            "peptide",
            "cosine",
            "leadingProtein",
            "proteinCosine",
            "peptideFDR",
            "leadingProteinFDR",
        ]


def test__identifier__main_workflow(commandLineArgs):
    identifier = Identifier(commandLineArgs)
    queryFile = commandLineArgs["input"][0]
    identifier._queryContext = QueryLoaderContext(queryFile)

    expectedMatchDf = pd.read_csv(
        get_file_from_system_test_folder("matchDf_precorrected.csv.gz"),
        compression="gzip",
    )
    matchDf = identifier._match_library_to_query_spectra()
    assert_numeric_pandas_dataframes_are_equal(expectedMatchDf, matchDf, "match")

    expectedCorrectedMatchDf = pd.read_csv(
        get_file_from_system_test_folder("matchDf_postcorrected.csv.gz"),
        compression="gzip",
    )
    matchDf = identifier._apply_correction_to_match_dataframe(matchDf)
    assert_numeric_pandas_dataframes_are_equal(
        expectedCorrectedMatchDf, matchDf, "match"
    )

    expectedScoreDf = pd.read_csv(
        get_file_from_system_test_folder("scoreDf.csv.gz"),
        compression="gzip",
    )
    scoreDf = identifier._score_spectra_matches(matchDf)
    assert_numeric_pandas_dataframes_are_equal(expectedScoreDf, scoreDf, "score")

    expectedFullDf = pd.read_csv(
        get_file_from_system_test_folder("v1FullOutput.csv.gz"), compression="gzip"
    )

    fullDf = identifier._format_identifications_as_dataframe(matchDf, scoreDf)

    assert_numeric_pandas_dataframes_are_equal(expectedFullDf, fullDf, "full")


def test__scoring_workflow():
    fullDf = pd.read_csv(
        get_file_from_system_test_folder("v2FullOutput.csv.gz"), compression="gzip"
    )
    expectedSpectralDf = pd.read_csv(
        get_file_from_system_test_folder("v1SpectralOutput.csv.gz"), compression="gzip"
    )
    expectedPeptideDf = pd.read_csv(
        get_file_from_system_test_folder("v1PeptideOutput.csv.gz"), compression="gzip"
    )
    expectedProteinDf = pd.read_csv(
        get_file_from_system_test_folder("v1ProteinOutput.csv.gz"), compression="gzip"
    )

    spectralDf = create_spectral_fdr_output_from_full_output(fullDf)
    assert_numeric_pandas_dataframes_are_equal(
        expectedSpectralDf, spectralDf, "spectral"
    )

    peptideDf = create_peptide_fdr_output_from_full_output(fullDf)
    assert_numeric_pandas_dataframes_are_equal(expectedPeptideDf, peptideDf, "peptide")

    proteinDf = create_protein_fdr_output_from_peptide_fdr_output(peptideDf)
    assert_numeric_pandas_dataframes_are_equal(expectedProteinDf, proteinDf, "protein")


def test__targeted_reanalysis_worflow():
    proteinDf = pd.read_csv(
        get_file_from_system_test_folder("v2ProteinOutput.csv.gz"), compression="gzip"
    )
    targetedOutputDict = create_mass_spec_input_dataframes_for_targeted_reanalysis_of_identified_peptides(
        proteinDf,
        isIncludeHeavyIsotopes=True,
        maximumPeptidesPerProtein=1,
        binValueProximity=0.75,
    )
    targetedOutputDict["fullDf"] = targetedOutputDict["fullDf"].drop(
        ["fileName"], axis=1
    )

    expectedAllCVDf = pd.read_csv(get_file_from_system_test_folder("allCVs.csv"))
    expectedAllCVDf = expectedAllCVDf.drop(["fileName"], axis=1)
    expected30Df = pd.read_csv(
        get_file_from_system_test_folder(
            "targetedReanalysis_mostIntenseTargs_CV_30.txt"
        ),
        sep="\t",
    ).fillna("")
    expected40Df = pd.read_csv(
        get_file_from_system_test_folder(
            "targetedReanalysis_mostIntenseTargs_CV_40.txt"
        ),
        sep="\t",
    ).fillna("")
    expected50Df = pd.read_csv(
        get_file_from_system_test_folder(
            "targetedReanalysis_mostIntenseTargs_CV_50.txt"
        ),
        sep="\t",
    ).fillna("")
    expected60Df = pd.read_csv(
        get_file_from_system_test_folder(
            "targetedReanalysis_mostIntenseTargs_CV_60.txt"
        ),
        sep="\t",
    ).fillna("")
    expected70Df = pd.read_csv(
        get_file_from_system_test_folder(
            "targetedReanalysis_mostIntenseTargs_CV_70.txt"
        ),
        sep="\t",
    ).fillna("")
    expected80Df = pd.read_csv(
        get_file_from_system_test_folder(
            "targetedReanalysis_mostIntenseTargs_CV_80.txt"
        ),
        sep="\t",
    ).fillna("")

    for column in targetedOutputDict["fullDf"].columns:
        expectedColumn = np.array(expectedAllCVDf[column])
        column = np.array(targetedOutputDict["fullDf"][column])
        if expectedColumn.dtype.kind in np.typecodes["AllFloat"]:
            np.testing.assert_array_almost_equal(expectedColumn, column)
        else:
            np.testing.assert_array_equal(expectedColumn, column)
    assert expected30Df.equals(targetedOutputDict["CV_30"])
    assert expected40Df.equals(targetedOutputDict["CV_40"])
    assert expected50Df.equals(targetedOutputDict["CV_50"])
    assert expected60Df.equals(targetedOutputDict["CV_60"])
    assert expected70Df.equals(targetedOutputDict["CV_70"])
    assert expected80Df.equals(targetedOutputDict["CV_80"])