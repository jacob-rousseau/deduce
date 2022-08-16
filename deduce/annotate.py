""" The annotate module contains the code for annotating text"""

import re
from abc import abstractmethod
from typing import Callable, Optional

import docdeid
from docdeid.datastructures import LookupList
from nltk.metrics import edit_distance

from deduce import utility
from deduce.lookup.lookup_lists import get_lookup_lists
from deduce.lookup.lookup_tries import get_lookup_tries
from deduce.tokenizer import Tokenizer

from docdeid.annotation.annotator import RegexpAnnotator


def _initialize():

    lookup_lists = get_lookup_lists()

    trie_merge_terms = LookupList()
    trie_merge_terms.add_items_from_iterable(["A1", "A2", "A3", "A4", "\n", "\r", "\t"])
    trie_merge_terms += lookup_lists["interfixes"]
    trie_merge_terms += lookup_lists["prefixes"]

    tokenizer = Tokenizer(merge_terms=trie_merge_terms)

    lookup_tries = get_lookup_tries(tokenizer)

    return lookup_lists, lookup_tries, tokenizer


_lookup_lists, _lookup_tries, tokenizer = _initialize()


class DeduceAnnotator(docdeid.BaseAnnotator):
    def annotate(self, document: docdeid.Document):

        annotations = self.annotate_structured(
            document.text, **document.get_meta_data()
        )

        document.add_annotations(annotations)

    @abstractmethod
    def annotate_structured(self, text: str, **kwargs) -> list[docdeid.Annotation]:
        pass


class InTextAnnotator(DeduceAnnotator):
    def __init__(self, flatten_function: Optional[Callable] = None):

        self.flatten_function = flatten_function or utility.flatten_text_all_phi

    def annotate_structured(self, text: str, **kwargs) -> list[docdeid.Annotation]:

        text = text.replace("<", "(")
        text = text.replace(">", ")")

        intext_annotated = self.annotate_intext(text, **kwargs)
        intext_annotated = self.flatten_function(intext_annotated)

        if intext_annotated == text:
            return list()

        tags = utility.find_tags(intext_annotated)
        shift = utility.get_shift(text, intext_annotated)

        # utility.get_annotations does not handle nested tags, so make sure not to pass it text with nested tags
        # Also, utility.get_annotations assumes that all tags are listed in the order they appear in the text
        annotations = utility.get_annotations(intext_annotated, tags, shift)

        # Check if there are any annotations whose start+end do not correspond to the text in the annotation
        mismatched_annotations = [
            ann
            for ann in annotations
            if text[ann.start_char : ann.end_char] != ann.text
        ]

        if len(mismatched_annotations) > 0:
            print(
                "WARNING:",
                len(mismatched_annotations),
                "annotations have texts that do not match the original text",
            )

        return annotations

    @abstractmethod
    def annotate_intext(self, text: str, **kwargs) -> str:
        pass


class NamesAnnotator(InTextAnnotator):
    def annotate_intext(self, text: str, **kwargs) -> str:

        text = self.annotate_names(text, **kwargs)
        text = self.annotate_names_context(text)

        return text

    def annotate_names(self, text: str, **kwargs) -> str:

        patient_first_names = kwargs.get("patient_first_names", "")
        patient_initials = kwargs.get("patient_initials", "")
        patient_surname = kwargs.get("patient_surname", "")
        patient_given_name = kwargs.get("patient_given_name", "")

        # Tokenize the text
        tokens = tokenizer.tokenize(text + " ")
        tokens_deid = []
        token_index = -1

        # Iterate over all tokens
        while token_index < len(tokens) - 1:

            # Current position
            token_index = token_index + 1

            # Current token, and number of tokens already deidentified (used to detect changes)
            token = tokens[token_index]
            num_tokens_deid = len(tokens_deid)

            # The context of this token
            (_, _, next_token, next_token_index) = utility.context(tokens, token_index)

            ### Prefix based detection
            # Check if the token is a prefix, and the next token starts with a capital
            prefix_condition = (
                token.lower() in _lookup_lists["prefixes"]
                and next_token != ""
                and next_token[0].isupper()
                and next_token.lower() not in _lookup_lists["whitelist"]
            )

            # If the condition is met, tag the tokens and continue to the next position
            if prefix_condition:
                tokens_deid.append(
                    f"<PREFIXNAAM {tokenizer.join_tokens(tokens[token_index: next_token_index + 1])}>"
                )
                token_index = next_token_index
                continue

            ### Interfix based detection
            # Check if the token is an interfix, and the next token is in the list of interfix surnames
            interfix_condition = (
                token.lower() in _lookup_lists["interfixes"]
                and next_token != ""
                and next_token in _lookup_lists["interfix_surnames"]
                and next_token.lower() not in _lookup_lists["whitelist"]
            )

            # If condition is met, tag the tokens and continue to the new position
            if interfix_condition:
                tokens_deid.append(
                    f"<INTERFIXNAAM {tokenizer.join_tokens(tokens[token_index: next_token_index + 1])}>"
                )
                token_index = next_token_index
                continue

            ### First name
            # Check if there is any information in the first_names variable
            if len(patient_first_names) > 1:

                # Because of the extra nested loop over first_names,
                # we can decide if the token has been tagged
                found = False

                # Voornamen
                for patient_first_name in str(patient_first_names).split(" "):

                    # Check if the initials match
                    if token == patient_first_name[0]:

                        # If followed by a period, also annotate the period
                        if next_token != "" and tokens[token_index + 1][0] == ".":
                            tokens_deid.append(
                                f"<INITIAALPAT {tokenizer.join_tokens([tokens[token_index], '.'])}>"
                            )
                            if tokens[token_index + 1] == ".":
                                token_index += 1
                            else:
                                tokens[token_index + 1] = tokens[token_index + 1][1:]

                        # Else, annotate the token itself
                        else:
                            tokens_deid.append(f"<INITIAALPAT {token}>")

                        # Break the first names loop
                        found = True
                        break

                    # Check that either an exact match exists, or a fuzzy match
                    # if the token has more than 3 characters
                    first_name_condition = token == patient_first_name or (
                        len(token) > 3
                        and edit_distance(
                            token, patient_first_name, transpositions=True
                        )
                        <= 1
                    )

                    # If the condition is met, tag the token and move on
                    if first_name_condition:
                        tokens_deid.append(f"<VOORNAAMPAT {token}>")
                        found = True
                        break

                # If a match was found, continue
                if found:
                    continue

            ### Initial
            # If the initial is not empty, and the token matches the initial, tag it as an initial
            if len(patient_initials) > 0 and token == patient_initials:
                tokens_deid.append(f"<INITIALENPAT {token}>")
                continue

            ### Surname
            if len(patient_surname) > 1:

                # Surname can consist of multiple tokens, so we will match for that
                surname_pattern = tokenizer.tokenize(patient_surname)

                # Iterate over all tokens in the pattern
                counter = 0
                match = False

                # See if there is a fuzzy match, and if there are enough tokens left
                # to match the rest of the pattern
                if edit_distance(
                    token, surname_pattern[0], transpositions=True
                ) <= 1 and (token_index + len(surname_pattern)) < len(tokens):

                    # Found a match
                    match = True

                    # Iterate over rest of pattern to see if every element matches (fuzzily)
                    while counter < len(surname_pattern):

                        # If the distance is too big, disregard the match
                        if (
                            edit_distance(
                                tokens[token_index + counter],
                                surname_pattern[counter],
                                transpositions=True,
                            )
                            > 1
                        ):
                            match = False
                            break

                        counter += 1

                # If a match was found, tag the appropriate tokens, and continue
                if match:
                    tokens_deid.append(
                        f"<ACHTERNAAMPAT {tokenizer.join_tokens(tokens[token_index: token_index + len(surname_pattern)])}>"
                    )
                    token_index = token_index + len(surname_pattern) - 1
                    continue

            ### Given name
            # Match if the given name is not empty, and either the token matches exactly
            # or fuzzily when more than 3 characters long
            given_name_condition = len(patient_given_name) > 1 and (
                token == patient_given_name
                or (
                    len(token) > 3
                    and edit_distance(
                        token, str(patient_given_name), transpositions=True
                    )
                    <= 1
                )
            )

            # If match, tag the token and continue
            if given_name_condition:
                tokens_deid.append(f"<ROEPNAAMPAT {token}>")
                continue

            ### Unknown first and last names
            # For both first and last names, check if the token
            # is on the lookup list and not on the whitelist
            if (
                token in _lookup_lists["first_names"]
                and token.lower() not in _lookup_lists["whitelist"]
            ):
                tokens_deid.append(f"<VOORNAAMONBEKEND {token}>")
                continue

            if (
                token in _lookup_lists["surnames"]
                and token.lower() not in _lookup_lists["whitelist"]
            ):
                tokens_deid.append(f"<ACHTERNAAMONBEKEND {token}>")
                continue

            ### Wrap up
            # Nothing has been added (ie no deidentification tag) to tokens_deid,
            # so we can safely add the token itself
            if len(tokens_deid) == num_tokens_deid:
                tokens_deid.append(token)

        # Return the deidentified tokens as a piece of text
        return tokenizer.join_tokens(tokens_deid).strip()

    def annotate_names_context(self, text: str) -> str:

        # Tokenize text and initiate a list of deidentified tokens
        tokens = tokenizer.tokenize(text + " ")
        tokens_deid = []
        token_index = -1

        # Iterate over all tokens
        while token_index < len(tokens) - 1:

            # Current token position
            token_index = token_index + 1

            # Current token
            token = tokens[token_index]

            # Number of tokens, used to detect change
            numtokens_deid = len(tokens_deid)

            # Context of the token
            (
                previous_token,
                previous_token_index,
                next_token,
                next_token_index,
            ) = utility.context(tokens, token_index)

            ### Initial or unknown capitalized word, detected by a name or surname that is behind it
            # If the token is an initial, or starts with a capital
            initial_condition = (
                utility.is_initial(token)
                or (
                    token != ""
                    and token[0].isupper()
                    and token.lower() not in _lookup_lists["whitelist"]
                )
            ) and (
                # And the token is followed by either a
                # found surname, interfix or initial
                "ACHTERNAAM" in next_token
                or "INTERFIX" in next_token
                or "INITIAAL" in next_token
            )

            # If match, tag the token and continue
            if initial_condition:
                tokens_deid.append(
                    f"<INITIAAL {tokenizer.join_tokens(tokens[token_index: next_token_index + 1])}>"
                )
                token_index = next_token_index
                continue

            ### Interfix preceded by a name, and followed by a capitalized token

            # If the token is an interfix
            interfix_condition = (
                token in _lookup_lists["interfixes"]
                and
                # And the token is preceded by an initial, found initial or found name
                (
                    utility.is_initial(previous_token)
                    or "INITIAAL" in previous_token
                    or "NAAM" in previous_token
                )
                and
                # And the next token must be capitalized
                next_token != ""
                and (next_token[0].isupper() or next_token[0] == "<")
            )

            # If the condition is met, tag the tokens and continue
            if interfix_condition:
                # Remove some already identified tokens, to prevent double tagging
                (_, previous_token_index_deid, _, _) = utility.context(
                    tokens_deid, len(tokens_deid)
                )
                deid_tokens_to_keep = tokens_deid[previous_token_index_deid:]
                tokens_deid = tokens_deid[:previous_token_index_deid]
                tokens_deid.append(
                    "<INTERFIXACHTERNAAM {}>".format(
                        tokenizer.join_tokens(
                            deid_tokens_to_keep
                            + tokens[token_index : next_token_index + 1]
                        )
                    )
                )
                token_index = next_token_index
                continue

            ### Initial or name, followed by a capitalized word
            # If the token is an initial, or found name or prefix
            initial_name_condition = (
                (
                    utility.is_initial(token)
                    or "VOORNAAM" in token
                    or "ROEPNAAM" in token
                    or "PREFIX" in token
                    # And the next token is uppercase and has at least 3 characters
                )
                and len(next_token) > 3
                and next_token[0].isupper()
                and next_token.lower() not in _lookup_lists["whitelist"]
            )

            # If a match is found, tag and continue
            if initial_name_condition:
                tokens_deid.append(
                    f"<INITIAALHOOFDLETTERNAAM {tokenizer.join_tokens(tokens[token_index: next_token_index + 1])}>"
                )
                token_index = next_token_index
                continue

            ### Patients A and B pattern

            # If the token is "en", and the previous token is tagged, and the next token is capitalized
            and_pattern_condition = (
                token == "en"
                and len(previous_token) > 0
                and len(next_token) > 0
                and "<" in previous_token
                and next_token[0].isupper()
            )

            # If a match is found, tag and continue
            if and_pattern_condition:
                (
                    previous_token_deid,
                    previous_token_index_deid,
                    _,
                    _,
                ) = utility.context(tokens_deid, len(tokens_deid))
                tokens_deid = tokens_deid[:previous_token_index_deid]
                tokens_deid.append(
                    f"<MEERDEREPERSONEN {tokenizer.join_tokens([previous_token_deid] + tokens[previous_token_index + 1: next_token_index + 1])}>"
                )
                token_index = next_token_index
                continue

            # Nothing has been added (ie no deidentification tag) to tokens_deid,
            # so we can safely add the token itself
            if len(tokens_deid) == numtokens_deid:
                tokens_deid.append(token)

        # Join the tokens again to form the de-identified text
        textdeid = tokenizer.join_tokens(tokens_deid).strip()

        if textdeid == text:
            return text

        return self.annotate_names_context(textdeid)


class InstitutionAnnotator(InTextAnnotator):
    @staticmethod
    def _replace_altrecht_text(match: re.Match) -> str:
        """
        <INSTELLING Altrecht> (with Altrecht in any casing) followed by words that start with capital letters is annotated
        as <INSTELLING Altrecht Those Words>, where Altrecht retains the original casing
        :param match: the match object from a regular expression search
        :return: the final string
        """
        return (
            match.group(0)[: len(match.group(0)) - len(match.group(1)) - 1]
            + match.group(1)
            + ">"
        )

    def annotate_intext(self, text: str, **kwargs) -> str:

        """Annotate institutions"""

        # Tokenize, and make a list of non-capitalized tokens (used for matching)
        tokens = tokenizer.tokenize(text)
        tokens_lower = [x.lower() for x in tokens]
        tokens_deid = []
        token_index = -1

        # Iterate over all tokens
        while token_index < len(tokens) - 1:

            # Current token position and token
            token_index = token_index + 1
            token = tokens[token_index]

            # Find all tokens that are prefixes of the remainder of the lowercase text
            prefix_matches = _lookup_tries["institutions"].find_all_prefixes(
                tokens_lower[token_index:]
            )

            # If none, just append the current token and move to the next
            if len(prefix_matches) == 0:
                tokens_deid.append(token)
                continue

            # Else annotate the longest sequence as institution
            max_list = max(prefix_matches, key=len)
            joined_institution = tokenizer.join_tokens(
                tokens[token_index : token_index + len(max_list)]
            )
            tokens_deid.append("<INSTELLING {}>".format(joined_institution))
            token_index += len(max_list) - 1

        # Return
        text = tokenizer.join_tokens(tokens_deid)

        # Detect the word "Altrecht" followed by a capitalized word
        text = re.sub(
            "<INSTELLING [aA][lL][tT][rR][eE][cC][hH][tT]>((\s[A-Z]([\w]*))*)",
            self._replace_altrecht_text,
            text,
        )

        # Return the text
        return text


class ResidenceAnnotator(InTextAnnotator):
    def annotate_intext(self, text: str, **kwargs) -> str:

        """Annotate residences"""

        # Tokenize text
        tokens = tokenizer.tokenize(text)
        tokens_deid = []
        token_index = -1

        # Iterate over tokens
        while token_index < len(tokens) - 1:

            # Current token position and token
            token_index = token_index + 1
            token = tokens[token_index]

            # Find all tokens that are prefixes of the remainder of the text
            prefix_matches = _lookup_tries["residences"].find_all_prefixes(
                tokens[token_index:]
            )

            # If none, just append the current token and move to the next
            if len(prefix_matches) == 0:
                tokens_deid.append(token)
                continue

            # Else annotate the longest sequence as residence
            max_list = max(prefix_matches, key=len)
            tokens_deid.append(f"<LOCATIE {tokenizer.join_tokens(max_list)}>")
            token_index += len(max_list) - 1

        # Return the de-identified text
        return tokenizer.join_tokens(tokens_deid)


class AddressAnnotator(InTextAnnotator):
    @staticmethod
    def _get_address_match_replacement(match: re.Match) -> str:
        text = match.group(0)
        stripped = text.strip()
        if len(text) == len(stripped):
            return f"<LOCATIE {text}>"

        return f"<LOCATIE {stripped}>{' ' * (len(text) - len(stripped))}"

    def annotate_intext(self, text: str, **kwargs) -> str:
        """Annotate addresses"""
        text = re.sub(
            r"([A-Z]\w+(straat|laan|hof|plein|plantsoen|gracht|kade|weg|steeg|steeg|pad|dijk|baan|dam|dreef|"
            r"kade|markt|park|plantsoen|singel|bolwerk)[\s\n\r]((\d+){1,6}(\w{0,2})?|(\d+){0,6}))",
            self._get_address_match_replacement,
            text,
        )
        return text


class PostalcodeAnnotator(InTextAnnotator):
    def annotate_intext(self, text: str, **kwargs) -> str:

        """Annotate postal codes"""
        text = re.sub(
            "(((\d{4} [A-Z]{2})|(\d{4}[a-zA-Z]{2})))(?P<n>\W)(?![^<]*>)",
            "<LOCATIE \\1>\\5",
            text,
        )
        text = re.sub("<LOCATIE\s(\d{4}mg)>", "\\1", text)
        text = re.sub("([Pp]ostbus\s\d{5})", "<LOCATIE \\1>", text)
        return text


class PhoneNumberAnnotator(InTextAnnotator):
    def annotate_intext(self, text: str, **kwargs) -> str:
        """Annotate phone numbers"""
        text = re.sub(
            "(((0)[1-9]{2}[0-9][-]?[1-9][0-9]{5})|((\\+31|0|0031)[1-9][0-9][-]?[1-9][0-9]{6}))(?![^<]*>)",
            "<TELEFOONNUMMER \\1>",
            text,
        )

        text = re.sub(
            "(((\\+31|0|0031)6){1}[-]?[1-9]{1}[0-9]{7})(?![^<]*>)",
            "<TELEFOONNUMMER \\1>",
            text,
        )

        text = re.sub(
            "((\(\d{3}\)|\d{3})\s?\d{3}\s?\d{2}\s?\d{2})(?![^<]*>)",
            "<TELEFOONNUMMER \\1>",
            text,
        )

        return text


class PatientNumerAnnotator(InTextAnnotator):
    def annotate_intext(self, text: str, **kwargs) -> str:
        """Annotate patient numbers"""
        text = re.sub("(\d{7})(?![^<]*>)", "<PATIENTNUMMER \\1>", text)
        return text


class DateAnnotator(InTextAnnotator):
    @staticmethod
    def _get_date_replacement_(date_match: re.Match, punctuation_name: str) -> str:
        punctuation = date_match[punctuation_name]
        if len(punctuation) != 1:
            punctuation = " "
        return "<DATUM " + date_match.group(1) + ">" + punctuation

    def annotate_intext(self, text: str, **kwargs) -> str:

        # Name the punctuation mark that comes after a date, for replacement purposes
        punctuation_name = "n"
        text = re.sub(
            "(([1-9]|0[1-9]|[12][0-9]|3[01])[- /.](0[1-9]|1[012]|[1-9])([- /.]{,2}(\d{4}|\d{2})){,1})(?P<"
            + punctuation_name
            + ">\D)(?![^<]*>)",
            lambda date_match: self._get_date_replacement_(
                date_match, punctuation_name
            ),
            text,
        )
        text = re.sub(
            "(\d{1,2}[^\w]{,2}(januari|februari|maart|april|mei|juni|juli|augustus|september|oktober|november|december)([- /.]{,2}(\d{4}|\d{2})){,1})(?P<"
            + punctuation_name
            + ">\D)(?![^<]*>)",
            lambda date_match: self._get_date_replacement_(
                date_match, punctuation_name
            ),
            text,
        )
        return text


class AgeAnnotator(RegexpAnnotator):

    def __init__(self):

        age_pattern = re.compile(
            "(\d{1,3})([ -](jarige|jarig|jaar))"
        )

        super().__init__(
            regexp_patterns=[age_pattern],
            category="LEEFTIJD",
            capturing_group=1
        )


class UrlAnnotator(RegexpAnnotator):

    def __init__(self):

        url_pattern_1 = re.compile(
            "((?!mailto:)(?:(?:http|https|ftp)://)(?:\\S+(?::\\S*)?@)?(?:(?:(?:[1-9]\\d?|1\\d\\d|2[01]\\d|22[0-3])(?:\\.(?:1?\\d{1,2}|2[0-4]\\d|25[0-5])){2}(?:\\.(?:[0-9]\\d?|1\\d\\d|2[0-4]\\d|25[0-4]))|(?:(?:[a-z\\u00a1-\\uffff0-9]+-?)*[a-z\\u00a1-\\uffff0-9]+)(?:\\.(?:[a-z\\u00a1-\\uffff0-9]+-?)*[a-z\\u00a1-\\uffff0-9]+)*(?:\\.(?:[a-z\\u00a1-\\uffff]{2,})))|localhost)(?::\\d{2,5})?(?:(/|\\?|#)[^\\s]*)?)"
        )

        url_pattern_2 = re.compile(
            "([\w\d\.-]{3,}(\.)(nl|com|net|be)(/[^\s]+){,1})"
        )

        super().__init__(
            regexp_patterns=[url_pattern_1, url_pattern_2],
            category="URL"
        )


class EmailAnnotator(RegexpAnnotator):

    def __init__(self):

        email_pattern = re.compile(
            r'([\w-]+(?:\.[\w-]+)*)@((?:[\w-]+\.)*\w[\w-]{0,66})\.([a-z]{2,6}(?:\.[a-z]{2})?)'
        )

        super().__init__(
            regexp_patterns=[email_pattern],
            category="URL"
        )

