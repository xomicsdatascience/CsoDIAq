from csodiaq.loaders.library.LibraryLoaderContext import LibraryLoaderContext
from csodiaq.loaders.query.QueryLoaderContext import QueryLoaderContext
from csodiaq.identifier.poolingFunctions import generate_pooled_library_and_query_spectra_by_mz_windows
from csodiaq.identifier.matchingFunctions import match_library_to_query_pooled_spectra, eliminate_low_count_matches, eliminate_matches_below_fdr_cutoff
from csodiaq.identifier.scoringFunctions import score_library_to_query_matches, identify_all_decoys, determine_index_of_fdr_cutoff, filter_matches_by_ppm_offset_and_tolerance, calculate_ppm_offset_tolerance
from csodiaq.identifier.outputWritingFunctions import extract_metadata_from_match_and_score_dataframes, format_output_line, format_output_as_pandas_dataframe
import pandas as pd

class Identifier():
    """
    Class for identifying library peptides in input query spectra for mass spec DIA experiments.

    Extended Summary
    ----------------
    The purpose of this class is to consolidate the primary workflow of identifying peptides
        from a library file in mass spec DIA query files. This includes finding similar peaks
        between them both (matching) and eliminating false positive matches (scoring). There is
        an optional correction step that further eliminates false positive library-query peak
        matches, refining both the final scores and false positive peptide elimination.

    Attributes
    ----------
    _args : dictionary
        This dictionary references the arguments inserted by the end user.
    _libraryDict : dictionary
        A standardized representation of the library input file for use of the program.
            It is the output of the LibraryLoaderContext class.
    _decoySet : set
        A set containing all the keys of self._libraryDict that represent a decoy insert.
            Decoys are used to calculate the probability that a non-decoy match is a
            false positive.
    """

    def __init__(self, args):
        self._args = args
        self._libraryDict = LibraryLoaderContext(self._args["library"]).load_csodiaq_library_dict()
        self._decoySet = set([key for key,value in self._libraryDict.items() if value["isDecoy"]])

    def identify_library_spectra_in_queries(self):
        """
        The primary function called for matching library spectra to query spectra.
            This is the only public-facing function of the class.
        """
        for queryFile in self._args["files"]:
            self._queryContext = QueryLoaderContext(queryFile)
            matchDf = self._match_library_to_query_spectra()
            scoreDf = self._score_spectra_matches(matchDf)
            matchDf, scoreDf = self._apply_correction_to_dataframes(matchDf, scoreDf)
            self._write_identifications_to_dataframe(matchDf, scoreDf)

    def _match_library_to_query_spectra(self):
        """
        This function identifies peaks in library and query spectra that are within a similar
            m/z value. This function includes an initial filtering step that removes all
            library-query spectrum matches that contain fewer than 3 peak matches.

        Returns
        -------
        matchDf : pandas DataFrame
            A dataframe representing every library-query PEAK match. Each row represents a peak
                match, containing library/query identifiers, intensity, and parts-per-million (PPM)
                relative differences between their m/z values.
        """
        matchDfs = []
        for pooledLibPeaks, pooledQueryPeaks in generate_pooled_library_and_query_spectra_by_mz_windows(
                self._libraryDict, self._queryContext):
            matchDf = match_library_to_query_pooled_spectra(pooledLibPeaks, pooledQueryPeaks,
                                                            self._args["fragmentMassTolerance"])
            matchDf = eliminate_low_count_matches(matchDf)
            matchDfs.append(matchDf)
        return pd.concat(matchDfs)

    def _score_spectra_matches(self, matchDf):
        """
        This function applies a cosine similarity score to each library-query spectrum match.
            Additional scoring is used to enhance the elimination of false positives.

        Extended Summary
        ----------------
        Scores are both generated and used to filter out false positive matches in this function.
            The False Discovery Rate (FDR) is calculated for each match (both target and decoy),
            and all matches below a specific threshold (0.01, or 1 decoy per 99 targets) are
            removed.

        Parameters
        ----------
        matchDf : pandas DataFrame
            See output of self._match_library_to_query_spectra().

        Returns
        -------
        scoreDf : pandas DataFrame
            A dataframe representing every library-query SPECTRUM match. Each row represents a
                spectrum match containing library/query identifiers and scores calculated for
                that match (including the cosine similarity score).
        """
        scoreDf = score_library_to_query_matches(matchDf)
        isDecoyArray = identify_all_decoys(self._decoySet, scoreDf)
        scoreDfCutoffIdx = determine_index_of_fdr_cutoff(isDecoyArray)
        return scoreDf.iloc[:scoreDfCutoffIdx, :]

    def _apply_correction_to_dataframes(self, matchDf, scoreDf):
        """
        An expected ppm tolerance range is defined and applied to the match and score dataframes.

        Extended Summary
        ----------------
        PPM is used as a relative m/z comparison in defining peak matches. However, there is often
            a standard m/z offset the query spectra peaks demonstrate specific to the callibration
            of the machine that generated them. This offset cannot be immediately determined from
            the query data files, and requires an initial comparison with library spectra. Thus,
            the first matching analysis assumes all matches will have an offset of 0 within a wide
            tolerance. This function determines the exact offset of the query spectra and removes
            all peak matches outside the scope of this offset.

        Parameters
        ----------
        matchDf : pandas DataFrame
            See output of self._match_library_to_query_spectra().

        scoreDf : pandas DataFrame
            See output of self._score_spectra_matches().

        Returns
        -------
        matchDf : pandas DataFrame
            A filtered version of the matchDf input parameter, where peak matches with a ppm value
                outside the calculated expected range are removed. The removal of all spectral matches
                with fewer than 3 peak matches is repeated as well.

        scoreDf : pandas DataFrame
            The score dataframe is recalculated from the ground up using the filtered match dataframe.
        """
        if self._args["correction"] == -1:
            return matchDf, scoreDf
        matchDf = self._apply_correction_to_match_dataframe(matchDf, scoreDf)
        scoreDf = self._apply_correction_to_score_dataframe(matchDf, scoreDf)
        return matchDf, scoreDf

    def _apply_correction_to_match_dataframe(self, matchDf, scoreDf):
        aboveCutoffGroups = set(scoreDf.groupby(["libraryIdx", "queryIdx"]).groups)
        matchDf = eliminate_matches_below_fdr_cutoff(matchDf, aboveCutoffGroups)
        offset, tolerance = calculate_ppm_offset_tolerance(matchDf["ppmDifference"], self._args["correction"])
        matchDf = filter_matches_by_ppm_offset_and_tolerance(matchDf, offset, tolerance)
        return eliminate_low_count_matches(matchDf)

    def _apply_correction_to_score_dataframe(self,  matchDf, scoreDf):
        scoreDf = score_library_to_query_matches(matchDf)
        isDecoyArray = identify_all_decoys(self._decoySet, scoreDf)
        scoreDfCutoffIdx = determine_index_of_fdr_cutoff(isDecoyArray)
        return scoreDf.iloc[:scoreDfCutoffIdx, :]

    def _write_identifications_to_dataframe(self, matchDf, scoreDf):
        """
        The final match/score identifications are consolidated and written to a single output
            .csv file.
        """

        matchDict = extract_metadata_from_match_and_score_dataframes(matchDf, scoreDf)
        queryDict = self._queryContext.extract_metadata_from_query_scans()
        sortedLibKeys = sorted(self._libraryDict.keys())
        outputs = []
        for key, matchMetadata in matchDict.items():
            libKeyIdx, queryScan = key
            libraryMetadata = self._prepare_library_dictionary_for_output(libKeyIdx, sortedLibKeys)
            queryMetadata = queryDict[str(queryScan)]
            queryMetadata["scan"] = queryScan
            outputLine = format_output_line(libraryMetadata, queryMetadata, matchMetadata)
            outputs.append(outputLine)
        outputDf = format_output_as_pandas_dataframe(self._queryContext.filePath, outputs)
        outFile = self._create_outfile_path()
        outputDf.to_csv(outFile, index=False)

    def _prepare_library_dictionary_for_output(self, libKeyIdx, sortedLibKeys):
        libKey = sortedLibKeys[libKeyIdx]
        libraryMetadata = self._libraryDict[libKey]
        libraryMetadata["precursorMz"] = libKey[0]
        libraryMetadata["peptide"] = libKey[1]
        return libraryMetadata

    def _create_outfile_path(self, ):
        outFileHeader = self._args['outDirectory'] + 'CsoDIAq-file' + '_' + '.'.join(
            self._queryContext.filePath.split('/')[-1].split('.')[:-1])
        if self._args['correction'] != -1:
            outFileHeader += '_corrected'
        return outFileHeader + '.csv'