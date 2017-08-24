""" utilities to help do comparisons in tests - esp. given that correct behavior here is (usually) not deterministic
"""
import logging
import string

from presswork.sanitize import unicode_dammit
from presswork.text.grammar import re_ascii_punctuation
from presswork.utils import iter_flatten

logger = logging.getLogger("presswork")


def destroy_punctuation(s):
    """ use bs4.UnicodeDammit to destroy stupid "smart quotes", then remove all ASCII punctuation

        >>> assert destroy_punctuation(string.punctuation) == ""
        >>> assert destroy_punctuation(string.punctuation + "hello" + string.punctuation) == "hello"
        >>> assert destroy_punctuation(string.punctuation + "can't" + string.punctuation) == "cant"
        >>> with_smart_quotes = b"I just \x93love\x94 your word processor\x92s smart quotes"
        >>> assert destroy_punctuation(with_smart_quotes) == 'I just love your word processors smart quotes'
    """
    cleaned = unicode_dammit(s)
    return re_ascii_punctuation.sub(u'', cleaned)


class WordSetComparison(object):
    """ Compares set-of-words in output text (generated) and input text (source text for model)

    Helps to check on a property of (our) markov-chain-text-generators: output words are a subset of input words.

    Refactored to a method-object for pragmatic reasons: w/ py.test, we have this great ability to showlocals
     when something goes wrong, and/or to drop into debugger. more instant gratification if the whole scope of
     this comparison is "there" in the test case scope too. (have confirmed, it is nice to debug with, this way.)

    >>> assert WordSetComparison(["exact"], ["exact"]).output_is_subset_of_input
    >>> assert WordSetComparison([["x", "y", "z"], "nest"], [["x", "y", "z", "abc"], "nest"]).output_is_subset_of_input
    >>> comparison = WordSetComparison(["off", "script"], ["input", "words"], quiet=True)
    >>> assert not comparison.output_is_subset_of_input
    >>> import pytest
    >>> with pytest.raises(ValueError): WordSetComparison("", "").output_is_subset_of_input
    """

    def __init__(self, generated_tokens, input_tokenized, quiet=False):
        """
        :param generated_tokens: words generated by make_sentences(). it can be nested; will flatten if needed.
        :param input_tokenized: words tokenized from input text. it can be nested; will flatten if needed.

        note, tokenization must be same on 'output' and 'input' - compare like with like.
        """
        self.quiet = quiet

        if isinstance(generated_tokens, basestring) or isinstance(input_tokenized, basestring):
            raise ValueError('please only pass already-tokenized items for comparison.')

        self._generated_tokens = iter_flatten(generated_tokens)
        self._input_tokenized = iter_flatten(input_tokenized)

        self.set_of_generated_words = set(self._clean_words(self._generated_tokens))
        self.set_of_input_words = set(self._clean_words(self._input_tokenized))

        # avoid comparing empty set(s). (why: set().issubsetof({1,2,3}) == True, but that doesn't mean much for us.)
        if not self.set_of_generated_words or not self.set_of_input_words:
            raise ValueError("this test is not meaningful if either word-set is empty. check for other errors!")

        self._difference = None

    @property
    def output_is_subset_of_input(self):
        """ A property of (our) markov-chain-text-generators: output words are a subset of input words. Check this.
        """
        is_subset = self.set_of_generated_words.issubset(self.set_of_input_words)

        if not is_subset and not self.quiet:
            self._troubleshoot_differences()

        return is_subset

    @property
    def difference(self):
        if self._difference is None:
            self._difference = self.set_of_generated_words.difference(self.set_of_input_words)
        return self._difference

    def _clean_words(self, words):
        """ strip away noise from the words, i.e. remove punctuation
        """
        return filter(None, (destroy_punctuation(word) for word in words))

    def _troubleshoot_differences(self):
        """ as an aid to troubleshooting, when there is a difference, "yell" about details on stdout.

        (pytest captures stdout then shows it only on failure: good fit for this. (better fit than logging to file.))
        """
        print "||| {} _troubleshoot_differences()".format(self.__class__.__name__)

        print "*" * 80
        print "||| set difference: these 'words' were in generated-output but do not seem to be 'words' in the input"
        print "||| len(difference) = ", len(self.difference)
        for diff_item in self.difference:
            print "  * ", diff_item