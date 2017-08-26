# -*- coding: utf-8 -*-
""" building blocks for making new sentences+words from generative models; composition is encouraged (pun intended)

-------------------------------------------------------------------------------
usage notes -- TextMaker & subclasses are the main *entry* point
===============================================================================

    * most common usage is just create_text_maker(<text>). that uses default class, and default settings.
        but caller can also get them by a nickname (CLI needs this), or for more custom, directly instantiate classes.

        >>> import logging; logging.disable(logging.CRITICAL)
        >>> from presswork.text.grammar import rejoin
        >>> text_maker = create_text_maker(input_text="Foo is better than bar.")  # use default strategy
        >>> result = text_maker.make_sentences(1)
        >>> rejoin(result)
        u'Foo is better than bar.'
        >>> text = "Simple is better than complex. But complex is better than complicated."
        >>> text_maker = create_text_maker(input_text=text, strategy="crude")
        >>> result = text_maker.make_sentences(1000)
        >>> string = rejoin(result)  # TODO change to explicitly use NewlineJoinerStrategy for clarity
        >>> assert all("better than" in line for line in string.splitlines())
        >>> assert all(line.startswith("Simple") or line.startswith("But") for line in string.splitlines())
        >>> from presswork.text.grammar import SentenceTokenizerPunkt, WordTokenizerWhitespace
        >>> text_maker = TextMakerCrude(sentence_tokenizer=SentenceTokenizerPunkt())
        >>> assert text_maker.input_text("Foo is better than bar.")
        >>> assert "better than" in rejoin(text_maker.make_sentences(10))
        >>> custom = SentenceTokenizerPunkt(word_tokenizer=WordTokenizerWhitespace())
        >>> text_maker = TextMakerCrude(sentence_tokenizer=custom)
        >>> assert text_maker.input_text("This text was input to a customized text maker")
        >>> rejoin(text_maker.make_sentences(1))
        u'This text was input to a customized text maker'
        >>> # TODO demonstrate using other Joiners

        >>> # TODO joiners, proofreaders.

    * composition is encouraged for putting together further variants. this can be done on the fly.
        attributes such as TextMaker.strategy are *not* protected, so they can be accessed directly and customized.

    * natural language scope: minimal; assumption is that output will be supervised or edited.
        this package works with models that consider 'sentences' and 'words', in natural languages
        that read from left to right, with whitespace separation between words. it should be possible to
        go beyond just "English," but significant redesign would be needed for significantly different languages

-------------------------------------------------------------------------------
design notes -- TextMaker and its collaborators
===============================================================================

    * favor composition.
        * TextMaker subclasses should be basically adapters - adapting strategies to a common interface.
            (so most methods *should* be forward methods to other strategies. should avoid having its own logic.)
        * TextMaker subclasses should *not* implement their own parsing/unparsing (aka tokenizing/joining).
            Should be done by collaborators, so that those collaborators can be mixed and matched. See `grammar`

    * as maintainer, I want to keep TextMaker interface restricted to essentials. this is to reduce scope,
            but also as an exercise to see what the common-denominator essential interface is.
        * interface should work beyond just markov chains: can back by other text generation strategies,
            anything that takes <tokenized text>, models it <any way it wants>, then outputs N sentences.
            I think there's a space to explore, with "pipes and filters" working on streams of sentence and words.
        * keeping TextMaker interface minimal encourages separating the concerns: collaborators, such as tokenizer
            and joiner, can be mixed matched and composed
            which then supports more mix-and-match (experiment with different compositions of behaviors)
        * avoiding support of filesystem persistence from the TextMaker level for now. each backend has its own
            way of doing that, and it doesn't seem important for now to unify that behind an interface.
            iff needed, the strategies can be accessed directly for their own save & load of models.

    * as *USER* I might find features are missing from TextMaker, but I these notes-to-self:
        * realize you can access 'strategy' attribute for customizations, or to overwrite with another instance.
        * consider using the third-party libraries directly. iff doing this repeatedly, then can refactor,
            and wrap that up in another stategy or "preset"

"""
import logging

from presswork import constants
from presswork.sanitize import SanitizedString
from presswork.text import grammar
from presswork.text.markov import _crude_markov
from presswork.text.markov.thirdparty._markovify import MarkovifyLite
from presswork.text.markov.thirdparty._pymarkovchain import PyMarkovChainForked

logger = logging.getLogger("presswork")


class TextMakerIsLockedException(ValueError):
    """ raise when someone tries to mutate TextMaker input text/state size/ etc after it is already loaded & locked
    """


class BaseTextMaker(object):
    """ common-denominator interface for making text from a generative model - so far, from markov chain models

    Subclasses should be "lazy" until input_text() is called. after that, it "locks" and it can only make_sentences().
    Typical usage should use the `create_text_maker` factory within this module, all 'convenience' is moved to there,
    so we can keep the class constructors minimal and DRY.

    Q:  Why lock after input_text is called?
    A:  Trying to keep things easy, but safe. With at least 1 impl (PyMarkovChain), calling input_text() more than once
        caues issues. additionally, changing ngram_size after calling input_text() could cause astonishment.
        Instead of allowing for some cases and denying for others, we just keep it consistent/safe.

    See also: overall design notes at the header of the module, which covers TextMakers as well as collaborators.
    """

    def __init__(self, ngram_size=constants.DEFAULT_NGRAM_SIZE, sentence_tokenizer=None, joiner=None):
        """
        :param ngram_size: state size AKA window size AKA N-gram size.
            this needs to be known both at the generate/load of the model (i.e. markov chain),
            and at the text generation time (and they need to match).

        :param sentence_tokenizer: one of the tokenizers from `grammar` module, or something that quacks like one.
            defaults to the 'cheap' option, all based on whitespace.
            what's expected: sentence_tokenizer.tokenize() => [ [word, word, ...], [word, word, ...], ... ].

        note: the word_tokenizer strategy is pluggable too, but it is something you attach to a sentence_tokenizer.
        i.e. sentence_tokenizer=SentenceTokenizer(word_tokenizer=WordTokenizer). more details in `grammar` module.

        :param joiner: if not given, uses a default. this can be one of the joiners from the `grammar` module,
            or something that implements `.join()` for a list of word-lists (same structure as sentence_tokenizer)
        """
        self._ngram_size = ngram_size

        if not sentence_tokenizer:
            logger.debug("no sentence_tokenizer argument given, defaulting to cheapest tokenizers")
            sentence_tokenizer = grammar.create_sentence_tokenizer("just_whitespace")

        if callable(getattr(sentence_tokenizer, "tokenize", None)):
            self.sentence_tokenizer = sentence_tokenizer
        else:
            raise ValueError("sentence_tokenizer must implement a tokenize() method")

        if not joiner:
            joiner = grammar.create_joiner("just_whitespace")

        if callable(getattr(joiner, "join", None)):
            self.joiner = joiner
        else:
            raise ValueError("joiner must implement a join() method")

        # So far with only 1 strategy for this and only 1 planned, not exposing via argument,
        # just putting the default here.
        self.proofreader = grammar.StringProofreader()

        self._locked = False

    def make_sentences(self, count):
        """ Do the thing! After TextMaker has been trained from input_text(), we can generate new sentences from it.

        :param count: How many sentences to generate
        :return: Sentences! Structured as a list of word-lists (list of token-lists).
            (Fun fact: The `set()` of tokens generated, will be a subset of the tokens from the input.)
        :rtype: grammar.SentencesAsWordLists
        """
        return NotImplementedError()  # pragma: no cover

    def input_text(self, input_text):
        """ build a fresh model from input text. (does not generate text - call make_sentences() to generate text.)

        * base class input_text() is public and handles pre/post hook that is same for all variants.
        * each subclass implements _input_tokenized(), private, implements the strategy. (may just adapt/forward)
        implements the *common* parts (not specific to subclasses)

        main effect is to change the state of the instance. the instance stores the strategy, the strategy
         stores the markov chain model it learns from the input text.

        :return: (optional) also returns the tokenized input text; this is mainly relevant for testing purposes
        """
        if self.is_locked:
            raise TextMakerIsLockedException("locked! has input_text() already been called? (can only be called once)")

        input_text = SanitizedString(input_text)
        sentences_as_word_lists = self.sentence_tokenizer.tokenize(input_text)

        self._input_text(sentences_as_word_lists)
        self._lock()

        return sentences_as_word_lists

    def _input_text(self, sentences_as_word_lists):
        """ build a fresh model from this input text. (private; should contain the impl or adapter.)

        :param sentences_as_word_lists: list of lists. grammar.SentencesAsWordLists, or anything that quacks like that.
            typically passed in from self.sentence_tokenizer.tokenize()
        """
        raise NotImplementedError()  # pragma: no cover

    def join(self, sentences_as_word_lists, proofread=True):
        """ join back together to a string. convenience method, that simply forwards to `self.joiner.join()`
        :param sentences_as_word_lists: the output from `self.make_sentences()`
        :param proofread: whether to call `self.proofreader.format()` afterwards.
        :return: the string, ready for reading, display, etc.
        :rtype: basestring

        >>> # TODO show calling join() both with proofread=True and proofread=False
        """
        result = self.joiner.join(sentences_as_word_lists)
        if proofread:
            result = self.proofreader.format(result)
        return result

    @property
    def ngram_size(self):
        return self._ngram_size

    @ngram_size.setter
    def ngram_size(self, value):
        """ refuses to change ngram_size property if the TextMaker has been locked
        """
        if self.is_locked:
            raise TextMakerIsLockedException(
                    "locked! ngram_size cannot be changed after locking (such as after loading input text), "
                    "to avoid unintended mixing of ngram_size values")
        self._ngram_size = value

    def _lock(self):
        """ lock upon first input_text call, to avoid changing things after loading input text for the first time

        (this is private, subclasses or callers should not need to call it or think about it.)
        """
        self._locked = True

    @property
    def is_locked(self):
        return self._locked

    def clone(self):
        """ create a new instance with the same constructor arguments. (helps with a test, if nothing else)
        """
        if self.is_locked:
            raise TextMakerIsLockedException('instance is locked! copying might be unsafe, aborting for max safety')
        return self.__class__(ngram_size=self.ngram_size, sentence_tokenizer=self.sentence_tokenizer)

    def __repr__(self):
        return "{}(ngram_size={!r}, sentence_tokenizer={!r})".format(
                self.__class__.__name__, self.ngram_size, self.sentence_tokenizer)


class TextMakerPyMarkovChain(BaseTextMaker):
    """ text maker using `PyMarkovChainFork` strategy, comparable performance to Markovify

    Plays nice with Unicode
    """
    NICKNAME = 'pymc'

    def __init__(self, *args, **kwargs):
        super(TextMakerPyMarkovChain, self).__init__(*args, **kwargs)
        self.strategy = PyMarkovChainForked(
                window=self.ngram_size,
                db_file_path=None)

    def _input_text(self, sentences_as_word_lists):
        self.strategy.database_init(sentences_as_word_lists)

    def make_sentences(self, count):
        result = self.strategy.make_sentences_list(number=count)
        return grammar.SentencesAsWordLists(result)


class TextMakerCrude(BaseTextMaker):
    """ text maker using homegrown 'crude' implementation

    For most usages, the other strategies should be preferred. (why keep it around? see _crude_markov module header.)

    Plays nice with Unicode though.
    """
    NICKNAME = 'crude'

    def __init__(self, *args, **kwargs):
        super(TextMakerCrude, self).__init__(*args, **kwargs)
        self.strategy = _crude_markov
        self._model = {}

    def _input_text(self, sentences_as_word_lists):
        self._model = self.strategy.crude_markov_chain(sentences_as_word_lists, ngram_size=self.ngram_size)

    def make_sentences(self, count):
        iter_sentences_of_words = self.strategy.iter_make_sentences(
                crude_markov_model=self._model, ngram_size=self.ngram_size, count=count)
        return grammar.SentencesAsWordLists(iter_sentences_of_words)


class TextMakerMarkovify(BaseTextMaker):
    """ text maker using `markovify` lib (behind an adapter). this is the first strategy to reach for!

    YMMV when passing Unicode to Markovify.
    """
    NICKNAME = 'markovify'

    def __init__(self, *args, **kwargs):
        super(TextMakerMarkovify, self).__init__(*args, **kwargs)
        # The way Markovify is set up, initializing isn't very useful or clean unless you already have your input text
        # ... so we don't instantiate strategy here, instead we leave it None - lazy until _input_text() is called
        self.strategy = None

    def input_text(self, input_text):
        """ mostly just call super(), but adding a hook to log a warning about Markovify's unicode status
        """
        if isinstance(input_text, unicode) or (hasattr(input_text, "data") and isinstance(input_text.data, unicode)):
            logger.warning("Markovify does not officially support unicode, YMMV! "
                           "Markovify/unidecode may strip or replace your unicode with ASCII. ".format(input_text))
        return super(TextMakerMarkovify, self).input_text(input_text)

    def _input_text(self, sentences_as_word_lists):
        # markovify is strict about its input being exactly `list` of `list` (duck typing not allowed), so we convert.
        if hasattr(sentences_as_word_lists, 'unwrap'):
            sentences_as_word_lists = sentences_as_word_lists.unwrap()

        if not sentences_as_word_lists:
            # 'empty' SentencesAsWordList could be [[]] or []; other strategies don't care. markovify rejects [] though
            sentences_as_word_lists = [[]]

        self.strategy = MarkovifyLite(
                state_size=constants.DEFAULT_NGRAM_SIZE,
                parsed_sentences=sentences_as_word_lists)

    def make_sentences(self, count):
        sentences = []
        for i in xrange(0, count):
            sentences.append(self.strategy.make_sentence())
        return grammar.SentencesAsWordLists(sentences)


# ====================================================================================================

_classes_by_nickname = {klass.NICKNAME: klass for klass in BaseTextMaker.__subclasses__()}
TEXT_MAKER_NICKNAMES = _classes_by_nickname.keys()
DEFAULT_TEXT_MAKER_NICKNAME = "markovify"


def _get_text_maker_class(name_or_nickname):
    """ helper for the factory below, and test suite.
    """

    classes_by_name = {klass.__name__: klass for klass in BaseTextMaker.__subclasses__()}
    klass = classes_by_name.get(name_or_nickname, _classes_by_nickname.get(name_or_nickname, None))

    if klass is None:
        raise KeyError("could not find text maker class for {!r}".format(name_or_nickname))

    return klass


def create_text_maker(
        strategy=DEFAULT_TEXT_MAKER_NICKNAME,
        sentence_tokenizer=None,
        joiner=None,
        input_text=None,
        ngram_size=constants.DEFAULT_NGRAM_SIZE,
):
    """ convenience factory to just "gimme a text maker" without knowing exact module layout. nicknames supported.

    rationale: I *do* want an easy way for callers to make these, but I want to keep the classes minimal -
    little to no special logic in the constructors.

    :param strategy: specific nickname of class to use e.g. 'crude', 'pymc' 'markovify'
        can also just pass in an exact class. if not given, will use the default.
    :param sentence_tokenizer: (optional) an instance of sentence tokenizer - or a nickname such as
        'nltk', 'just_whitespace'. if not given, a TextMaker class will just use its default.
    :param joiner: (optional) an instance of joiner - or a nickname such as 'just_whitespace', 'moses'
    :param input_text: (optional) the input text to load into the TextMaker class.
        (if not given, can be loaded later load it later.)
    """
    text_maker_kwargs = {}

    try:
        ATextMakerClass = _get_text_maker_class(name_or_nickname=strategy)
    except KeyError:
        if callable(strategy):
            ATextMakerClass = strategy
        else:
            raise ValueError('{!r} does not appear to be a valid class nor nickname'.format(strategy))

    if sentence_tokenizer:
        try:
            ASentenceTokenizerClass = grammar.tokenizer_classes_by_nickname[sentence_tokenizer]
            sentence_tokenizer = ASentenceTokenizerClass()
        except KeyError:
            pass

        text_maker_kwargs["sentence_tokenizer"] = sentence_tokenizer

    if joiner:
        try:
            AJoinerClass = grammar.joiner_classes_by_nickname[joiner]
            joiner = AJoinerClass()
        except KeyError:
            pass

        text_maker_kwargs["joiner"] = joiner

    text_maker = ATextMakerClass(ngram_size=ngram_size, **text_maker_kwargs)

    if input_text is not None:
        # SanitizedString 'memoizes' to avoid redundant sanitization - so it's no problem to call redundantly
        input_text = SanitizedString(input_text)
        text_maker.input_text(input_text)

    return text_maker
