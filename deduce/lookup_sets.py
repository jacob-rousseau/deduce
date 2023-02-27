import os
from pathlib import Path

import docdeid as dd

from deduce.str.processor import (
    Acronimify,
    FilterBasedOnLookupSet,
    RemoveValues,
    TakeLastToken,
)


class LookupSetLoader:

    def __init__(self, config_dict):
        data_path_str = os.path.abspath(config_dict["lookup_lists_path"])
        self.data_path = Path(data_path_str)

    # body of the constructor
    def _load_first_names(self) -> dd.ds.LookupSet:
        """Get first names LookupSet."""

        first_names = dd.ds.LookupSet()

        first_names.add_items_from_file(
            os.path.join(self.data_path, "first_names.txt"),
            cleaning_pipeline=[dd.str.FilterByLength(min_len=2)],
        )

        return first_names

    def _load_surnames(self) -> dd.ds.LookupSet:
        """Get surnames LookupSet."""

        surnames = dd.ds.LookupSet()

        surnames.add_items_from_file(
            os.path.join(self.data_path, "surnames.txt"),
            cleaning_pipeline=[dd.str.FilterByLength(min_len=2)],
        )

        return surnames

    def _load_interfixes(self) -> dd.ds.LookupSet:
        """Get interfixes LookupSet ('van der', etc.)"""

        interfixes = dd.ds.LookupSet()

        interfixes.add_items_from_file(os.path.join(self.data_path, "interfixes.txt"))

        return interfixes

    def _load_interfix_surnames(self) -> dd.ds.LookupSet:
        """Get interfix surnames LookupSet (e.g. 'Jong' for 'de Jong')"""

        interfix_surnames = dd.ds.LookupSet()

        interfix_surnames.add_items_from_file(
            os.path.join(self.data_path, "interfix_surnames.txt"),
            cleaning_pipeline=[TakeLastToken()],
        )

        return interfix_surnames

    def _load_prefixes(self) -> dd.ds.LookupSet:
        """Get prefixes LookupSet (e.g. 'dr', 'mw')"""

        prefixes = dd.ds.LookupSet()

        prefixes.add_items_from_file(os.path.join(self.data_path, "prefixes.txt"))

        return prefixes

    def _load_whitelist(self) -> dd.ds.LookupSet:
        """
        Get whitelist LookupSet.

        Composed of medical terms, top 1000 frequent words (except surnames), and stopwords.
        Returns:
        """
        med_terms = dd.ds.LookupSet()
        med_terms.add_items_from_file(
            os.path.join(self.data_path, "medical_terms.txt"),
        )

        top1000 = dd.ds.LookupSet()
        top1000.add_items_from_file(
            os.path.join(self.data_path, "top_1000_terms.txt"),
        )

        surnames_lowercase = dd.ds.LookupSet()
        surnames_lowercase.add_items_from_file(
            os.path.join(self.data_path, "surnames.txt"),
            cleaning_pipeline=[
                dd.str.LowercaseString(),
                dd.str.FilterByLength(min_len=2),
            ],
        )

        top1000 = top1000 - surnames_lowercase

        stopwords = dd.ds.LookupSet()
        stopwords.add_items_from_file(os.path.join(self.data_path, "stop_words.txt"))

        whitelist = dd.ds.LookupSet(matching_pipeline=[dd.str.LowercaseString()])
        whitelist.add_items_from_iterable(
            med_terms + top1000 + stopwords,
            cleaning_pipeline=[dd.str.FilterByLength(min_len=2)],
        )

        return whitelist

    def _load_institutions(self) -> dd.ds.LookupSet:
        """Get institutions LookupSet."""

        institutions_raw = dd.ds.LookupSet()
        institutions_raw.add_items_from_file(
            os.path.join(self.data_path, "institutions.txt"),
            cleaning_pipeline=[dd.str.FilterByLength(min_len=3), dd.str.LowercaseString()],
        )

        institutions = dd.ds.LookupSet(matching_pipeline=[dd.str.LowercaseString()])
        institutions.add_items_from_iterable(institutions_raw, cleaning_pipeline=[dd.str.StripString()])

        institutions.add_items_from_iterable(
            institutions_raw,
            cleaning_pipeline=[
                RemoveValues(filter_values=["dr.", "der", "van", "de", "het", "'t", "in", "d'"]),
                dd.str.StripString(),
            ],
        )

        institutions.add_items_from_self(cleaning_pipeline=[dd.str.ReplaceValue(".", ""), dd.str.StripString()])

        institutions.add_items_from_self(cleaning_pipeline=[dd.str.ReplaceValue("st ", "sint ")])

        institutions.add_items_from_self(cleaning_pipeline=[dd.str.ReplaceValue("st. ", "sint ")])

        institutions.add_items_from_self(cleaning_pipeline=[dd.str.ReplaceValue("ziekenhuis", "zkh")])

        # Temporarily removed the acronimification of institutes. Leads to a lot of false-positives e.g. 'too' and 'are'
        # are annotated as PHI ([INSTELLING_XXX]).
        #institutions.add_items_from_self(
        #    cleaning_pipeline=[dd.str.LowercaseString(), Acronimify(), dd.str.FilterByLength(min_len=3)]
        #)

        institutions = institutions - self._load_whitelist()

        return institutions

    def _load_residences(self) -> dd.ds.LookupSet:
        """Get residences LookupSet."""

        residences = dd.ds.LookupSet()
        residences.add_items_from_file(
            file_path=os.path.join(self.data_path, "residences.txt"),
            cleaning_pipeline=[dd.str.ReplaceValueRegexp(r"\(.+\)", ""), dd.str.StripString()],
        )

        residences.add_items_from_self(cleaning_pipeline=[dd.str.ReplaceValue("-", " ")])

        residences.add_items_from_self(
            cleaning_pipeline=[FilterBasedOnLookupSet(filter_set=self._load_whitelist(), case_sensitive=False)],
            replace=True,
        )

        return residences

    def build_lookup_sets(self) -> dd.ds.DsCollection:
        """
        Get all lookupsets.

        Returns:
            A DsCollection with all lookup sets.
        """

        lookup_sets = dd.ds.DsCollection()

        lookup_sets["first_names"] = self._load_first_names()
        lookup_sets["surnames"] = self._load_surnames()
        lookup_sets["interfixes"] = self._load_interfixes()
        lookup_sets["interfix_surnames"] = self._load_interfix_surnames()
        lookup_sets["prefixes"] = self._load_prefixes()
        lookup_sets["whitelist"] = self._load_whitelist()
        lookup_sets["institutions"] = self._load_institutions()
        lookup_sets["residences"] = self._load_residences()

        return lookup_sets
