# -*- coding: utf-8 -*-
""" 'Legacy' but usable Markov Chain Text Maker class. Forked from PyMarkovCHain

------------------------------------------------------------------------------------------------------------
NOTES RE: AUTHORSHIP & CAVEATS
============================================================================================================

Forked from PyMarkovChain==1.7.5 MarkovChain class
(https://github.com/TehMillhouse/PyMarkovChain/tree/ade01f64b6107e426f6c01168aae14ad238c656f).
Its algorithm is left the (mostly) same, though I did refactor some things after forking.

I originally forked it to bring NLTK into the mix for tokenizing (Original class did not have good extension points.)
... but now, have hollowed it out further.

Markovify is preferable for most uses but this implementation is kept here as a contrast or fallback.
(Since this repo is non-utilitarian anyways. Nice excuse eh!)
"""

from __future__ import division

try:
    # try to use cPickle for better performance (python2)
    import cPickle as pickle
except ImportError:
    import pickle

from collections import defaultdict
import logging
import os
import random
import re

SPECIAL_TOKEN = u''



def _db_factory():
    """ DB data structure: dict like  {word_sequence: {next_word: probability}}
    """
    return defaultdict(_default_word_probability_dict)


def _default_word_probability_dict():
    """ defaultdict where each key has a value of 1.0 to start with (default probability)

    the keys will be "words"
    """
    return defaultdict(_one)


def _one():
    return 1.0


class EndOfChainException(Exception):
    pass


class PyMarkovChainForked(object):
    """ A text model and text maker in a single class, with options for local filesystem persistence.

    Forked from PyMarkovChain library's MarkovChain class (https://pypi.python.org/pypi/PyMarkovChain/)

    See module header for notes on AUTHORSHIP and CAVEATS.
    """
    # TODO this should use tmpdir
    DEFAULT_DB_FILE_PATH = os.path.join(os.path.dirname(__file__), "presswork_markov_db")
    DEFAULT_WINDOW_SIZE_WORDS = 2

    # data structure for this db is dictionaries nested 1 deep: `{words: {word: probability}}`
    def __init__(
            self,
            db_file_path=None,
            window=DEFAULT_WINDOW_SIZE_WORDS,
            sentence_tokenizer=None,
    ):
        self.window = window

        self.db = None
        self.db_file_path = db_file_path
        if self.db_file_path:
            try:
                with open(self.db_file_path, 'rb') as dbfile:
                    self.db = pickle.load(dbfile)
            except (IOError, ValueError):
                logging.debug('db_file_path given, but unreadable (not found, or corrupt), using empty database')

        if self.db is None:
            self.db = _db_factory()

        self._sentence_tokenizer = sentence_tokenizer

    #@DeprecationWarning TODO find usages, update to use something else, then delete this method
    @classmethod
    def with_persistence(self, db_file_path=DEFAULT_DB_FILE_PATH, **kwargs):
        return PyMarkovChainForked(db_file_path=db_file_path, **kwargs)

    @property
    def _special_ngram(self):
        # The original PyMarkovChain implementation used this as a beginning (regardless of ngram size)
        # ... I consider this "legacy" so I'm treading lightly in some ways, i.e. not removing this convention,
        # ... however I wanted to DRY up the usages a little.
        return (SPECIAL_TOKEN,)

    def increment_words(self, words):
        self.db[self._special_ngram][words[0]] += 1

    # TODO(hangtwenty) next step in parity tests is to get this to accept list-of-lists with no specific parsing...
    # i.e. parsing done by caller. then both crude & pymc can be using the same exact sentence-splitter & then the
    # case that asserts they are deterministic can work...
    def database_init(self, text_input):
        """ Generate word probability database from raw content string """
        # FIXME remove this overloading. it ishould only accept list-of-lists. just need to fixup those unit tests
        if isinstance(text_input, basestring):
            sentences_as_word_seqs = \
                self._sentence_tokenizer.tokenize(text_input)
        else:
            sentences_as_word_seqs = text_input
        # I'm using the database to temporarily store word counts
        # We need a special symbol for the beginning of a sentence.
        self.db[self._special_ngram][SPECIAL_TOKEN] = 0.0
        for word_seq in sentences_as_word_seqs:
            if len(word_seq) == 0:
                continue
            # first word follows a sentence end
            self.increment_words(word_seq)

            for order in range(1, self.window + 1):
                for i in range(len(word_seq) - 1):
                    if i + order >= len(word_seq):
                        continue
                    word = tuple(word_seq[i:i + order])
                    self.db[word][word_seq[i + order]] += 1

                # last word precedes a sentence end
                self.db[tuple(word_seq[len(word_seq) - order:len(word_seq)])][SPECIAL_TOKEN] += 1

        # We've now got the db filled with parametrized word counts
        # We still need to normalize this to represent probabilities
        for word in self.db:
            wordsum = 0
            for nextword in self.db[word]:
                wordsum += self.db[word][nextword]
            if wordsum != 0:
                for nextword in self.db[word]:
                    self.db[word][nextword] /= wordsum

    def database_dump(self):
        try:
            with open(self.db_file_path, 'wb') as dbfile:
                pickle.dump(self.db, dbfile)
            # It looks like db was written successfully
            return True
        except IOError:
            logging.warn('Database file could not be written')
            return False

    def database_clear(self):
        os.unlink(self.db_file_path)

    def make_sentences_list(self, number, seed_str=None):
        if seed_str:
            seed = self._seed_str_to_seed_tokens(seed_str)
        else:
            seed = self._special_ngram

        sentences = []
        for _ in range(0, number):
            sentences.append(self._generate_sentence_as_list(seed))

        return sentences

    # TODO(hangtwenty) get rid of these functions that stringify before returning (DEPRECATED...)
    #@DeprecationWarning
    def make_sentences(self, number):
        sentences = []
        for _ in range(0, number):
            sentences.append(self.make_sentence())
        generated = u"  ".join(sentences)
        return PyMarkovChainForked.post_process(generated)

    #@DeprecationWarning TODO find usages, update to use something else, then delete this method
    def make_sentence(self):
        """ Generate a "sentence" with the database of known text """
        generated = self._accumulate_with_seed(self._special_ngram)
        return PyMarkovChainForked.post_process(generated)

    #@DeprecationWarning TODO find usages, update to use something else, then delete this method
    def make_sentence_with_seed(self, seed):
        """ Generate a "sentence" with the database and a given word """
        words = self._seed_str_to_seed_tokens(seed)
        generated = self._accumulate_with_seed(words)
        return PyMarkovChainForked.post_process(generated)

    def _seed_str_to_seed_tokens(self, seed_str):
        # FIXME hmm, not very clear on its own but was refactored out because it's subtle and was duplicated.. (DRY up)
        # using str.split here means we're contructing the list in memory
        # but as the generated sentence only depends on the last word of the seed
        # I'm assuming seeds tend to be rather short.
        words = seed_str.split()
        if (words[-1],) not in self.db:
            # The only possible way it won't work is if the last word is not known
            raise EndOfChainException(u'Could not continue string: ' + seed_str)
        return words

    #@DeprecationWarning TODO find usages, update to use something else, then delete this method
    @staticmethod
    def post_process(string):
        string = PyMarkovChainForked._remove_space_before_phrase_end_punctuation(string)
        return string

    #@DeprecationWarning TODO for this specific one, get rid of in this class, but maybe move somewhere generic, it's handy
    @staticmethod
    def _remove_space_before_phrase_end_punctuation(string):
        """ Replace " . " with ". ", and so on, for other punctuation that probably ends sentences
        or clauses.
        """
        return re.sub(r'\s([.,!?:;](?:\s|$))', r'\1', string)

    def _generate_sentence_as_list(self, seed):
        """ Accumulate the generated sentence with a given single word as a
        seed """
        next_word = self._next_word(seed)
        sentence = list(seed) if seed else []
        while next_word:
            sentence.append(next_word)
            next_word = self._next_word(sentence)
        return sentence

    # TODO(hangtwenty) get rid of these functions that stringify before returning (DEPRECATED...)
    #@DeprecationWarning TODO find usages, update to use something else, then delete this method
    def _accumulate_with_seed(self, seed):
        """ Accumulate the generated sentence with a given single word as a
        seed """
        return ' '.join(self._generate_sentence_as_list(seed))

    def _next_word(self, last_words):
        last_words = tuple(last_words)
        if last_words != self._special_ngram:
            while last_words not in self.db:
                last_words = last_words[1:]
                if not last_words:
                    return SPECIAL_TOKEN
        probmap = self.db[last_words]
        sample = random.random()
        # since rounding errors might make us miss out on some words
        maxprob = 0.0
        maxprobword = SPECIAL_TOKEN
        for candidate in probmap:
            # remember which word had the highest probability
            # this is the word we'll default to if we can't find anything else
            if probmap[candidate] > maxprob:
                maxprob = probmap[candidate]
                maxprobword = candidate
            if sample > probmap[candidate]:
                sample -= probmap[candidate]
            else:
                return candidate
        # getting here means we haven't found a matching word. :(
        return maxprobword