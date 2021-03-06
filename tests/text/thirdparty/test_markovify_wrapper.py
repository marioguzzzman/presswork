""" tests the *wrapper* around Markovify - just that. more significant tests are in `test_essentials_and_parity`

this module should NOT test all of Markovify -
    - Markovify already has a test suite,
    - Markovify & our adapter (MarkovifyLite) get exercised plenty in text.text_makers

what's left is just to test some of the edges in the wrapper (which Coverage showed were not covered by other tests)
"""
import pytest

from presswork.text.markov.thirdparty import _markovify

quick_dirty_tokenize = lambda text: [[word.strip() for word in sent.split()] for sent in text.splitlines()]
input_text = "Roshi always said, too many people live like so: " \
             "If only... If only... If only ... Dead!"


def test_markovify_does_not_stringify_too_soon():
    tokenized = quick_dirty_tokenize(input_text)

    markovify_lite = _markovify.MarkovifyLite(parsed_sentences=tokenized)

    assert markovify_lite.make_sentence()

    # Markovify itself stringifies before returning. Confirm we have disabled that
    assert markovify_lite.make_sentence()
    assert not isinstance(markovify_lite.make_sentence(), basestring)

    # hitting one more un-covered line or two - stringifying methods that our wrapper neutralizes to no-ops
    assert markovify_lite.sentence_join(tokenized) == tokenized
    assert markovify_lite.word_join(tokenized) == tokenized


def test_markovify_disabled_features():
    markovify_lite = _markovify.MarkovifyLite(parsed_sentences=quick_dirty_tokenize(input_text))

    # Markovify itself wants to tokenize the text for you.
    # Confirm we have disabled this feature to keep that concern separate
    with pytest.raises(_markovify.Disabled):
        markovify_lite.generate_corpus(input_text)
    with pytest.raises(_markovify.Disabled):
        _markovify.MarkovifyLite(input_text=input_text)

    # This is a great feature of markovify
    with pytest.raises(_markovify.NotYetImplementedInAdapter):
        markovify_lite.test_sentence_output()
