import pandas as pd
import numpy as np
from csodiaq.scoring.scoringFunctions import (
    calculate_fdr_rates_of_decoy_array,
)
from csodiaq.utils import format_protein_list_to_string, format_protein_string_to_list


def format_output_line(libMetadata, queMetadata, matchMetadata):
    return [
        queMetadata["scan"],
        queMetadata["precursorMz"],
        libMetadata["peptide"],
        libMetadata["proteinName"],
        libMetadata["isDecoy"],
        libMetadata["precursorMz"],
        libMetadata["precursorCharge"],
        matchMetadata["cosineSimilarityScore"],
        libMetadata["identification"],
        queMetadata["peaksCount"],
        len(libMetadata["peaks"]),
        matchMetadata["shared"],
        matchMetadata["ionCount"],
        queMetadata["CV"],
        queMetadata["windowWidth"],
        matchMetadata["maccScore"],
        matchMetadata["exclude_num"],
    ]


def extract_metadata_from_match_and_score_dataframes(matchDf, scoreDf, queryDict):
    matchDict = {
        k: extract_metadata_from_match_dataframe_groupby(v, queryDict[str(k[1])])
        for k, v in matchDf.groupby(["libraryIdx", "queryIdx"])
    }
    scoreDict = extract_metadata_from_score_dataframe(scoreDf)
    metadataDict = {k: {**matchDict[k], **scoreDict[k]} for k in scoreDict.keys()}
    return metadataDict


def extract_metadata_from_match_dataframe_groupby(group, queryMetadata):
    precursorMz = queryMetadata["precursorMz"]
    groupRowsAbovePrecursorMz = group[group["queryMz"] > precursorMz]
    return {
        "shared": len(group.index),
        "ionCount": sum(groupRowsAbovePrecursorMz["queryIntensity"]),
        "exclude_num": len(group.index) - len(groupRowsAbovePrecursorMz),
    }


def extract_metadata_from_score_dataframe(df):
    maccDict = df.set_index(["libraryIdx", "queryIdx"])["maccScore"].to_dict()
    cosineDict = df.set_index(["libraryIdx", "queryIdx"])["cosineScore"].to_dict()
    outputDict = {
        k: {"maccScore": maccDict[k], "cosineSimilarityScore": cosineDict[k]}
        for k in maccDict.keys()
    }
    return outputDict


def format_output_as_pandas_dataframe(inputFileName, outputData):
    columns = [
        "scan",
        "MzEXP",
        "peptide",
        "protein",
        "isDecoy",
        "MzLIB",
        "zLIB",
        "cosine",
        "name",
        "Peak(Query)",
        "Peaks(Library)",
        "shared",
        "ionCount",
        "CompensationVoltage",
        "totalWindowWidth",
        "MaCC_Score",
        "exclude_num",
    ]
    outputDf = pd.DataFrame(outputData, columns=columns)
    outputDf.insert(0, "fileName", [inputFileName] * len(outputDf.index))
    return outputDf


def identify_all_decoys(decoySet, scoreDf):
    return np.where(scoreDf["libraryIdx"].isin(decoySet), 1, 0)