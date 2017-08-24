""" test TextMaker variants - esp. essential properties of markov chain text generators, and fundamental parity
"""
# -*- coding: utf-8 -*-
import pytest

import presswork.text.grammar
from presswork.text import grammar
from presswork.text import text_makers

from tests import helpers


@pytest.fixture(params=text_makers.CLASS_NICKNAMES)
def each_text_maker(request):
    """ get 1 text maker instance (doesn't load input_text; so, test cases control input_text, ngram_size)

    the fixture is parametrized so that test cases will get 'each' text_maker, 1 per test case

    this fixture should be used in tests where the criteria isn't specific to the text maker implementation,
    such as these essentials/parity texts.
    """
    name = request.param
    text_maker = text_makers.create_text_maker(class_or_nickname=name)
    return text_maker


@pytest.fixture()
def all_text_makers(request):
    """ get instances of ALL text maker variants (doesn't load input_text; test cases control input_text, ngram_size)

    this fixture should be used when we want multiple text maker varieties in one test, such as to confirm that
    under valid circumstances they behave similar (or same) for similar inputs
    """
    all_text_makers = []
    for name in text_makers.CLASS_NICKNAMES:
        text_maker = text_makers.create_text_maker(class_or_nickname=name)
        all_text_makers.append(text_maker)

    return all_text_makers


@pytest.mark.parametrize('ngram_size', range(2, 6))
@pytest.mark.parametrize('sentence_tokenizer', [
    grammar.SentenceTokenizerPunkt(word_tokenizer=grammar.WordTokenizerTreebank()),
    grammar.SentenceTokenizerPunkt(word_tokenizer=grammar.WordTokenizerWhitespace()),
    grammar.SentenceTokenizerWhitespace(word_tokenizer=grammar.WordTokenizerTreebank()),
])
def test_essential_properties_of_text_making(each_text_maker, ngram_size, sentence_tokenizer, text_any):
    """ confirm some essential known properties of text-making output, common to all the text makers
    :param each_text_maker: each text maker, injected by pytest from each_text_maker fixture.
    :param ngram_size: passed to text maker, here we test a 'reasonable' range (other cases test bigger range)
    :param sentence_tokenizer:  in practice the tokenizer choice is significant, however in test case we just try each.
        when tokenizer is same on input & output, it 'cancels out'.
        so we can take this opportunity to exercise many tokenizers, and affirm mix-and-match-ability
    :param text_any: a fixture from conftest.py: 1 at a time, will be each fixture from tests/fixtures/plaintext
    """
    text_maker = each_text_maker
    text_maker.ngram_size = ngram_size

    _input_tokenized = text_maker.input_text(text_any)

    sentences = text_maker.make_sentences(300)

    word_set_comparison = helpers.WordSetComparison(generated_tokens=sentences, input_tokenized=_input_tokenized)
    assert word_set_comparison.output_is_subset_of_input


@pytest.mark.parametrize('sentence_tokenizer', [
    grammar.SentenceTokenizerWhitespace(word_tokenizer=grammar.WordTokenizerWhitespace()),
])
def test_text_making_with_blankline_tokenizer(each_text_maker, sentence_tokenizer, text_newlines):
    """ covers some of same ground as test_essential_properties, but uses tokenizer that only works with line-separated
    :param text_newlines: 1 text at a time, but only fixture(s) where it is (mostly) newline separated
    """
    text_maker = each_text_maker

    _input_tokenized = text_maker.input_text(text_newlines)
    sentences = text_maker.make_sentences(200)

    word_set_comparison = helpers.WordSetComparison(generated_tokens=sentences, input_tokenized=_input_tokenized)
    assert word_set_comparison.output_is_subset_of_input

    # as a followup, let's double check that our comparison is valid (by confirming invalidated case would fail)
    _test_self_ensure_test_would_fail_if_comparison_was_invalid(
            generated_tokens=sentences, input_tokenized=_input_tokenized)


@pytest.mark.parametrize('ngram_size', range(2, 12))
def test_easy_deterministic_cases_are_same_for_all_text_makers(all_text_makers, text_easy_deterministic, ngram_size):
    """ Any TextMaker will return deterministic results from seq of words w/ no duplicates; all strategies should match

    (btw high ngram_sizes aren't very useful, but included here because sparks should not fly...!)
    """
    outputs = {}
    for text_maker in all_text_makers:
        text_maker.ngram_size = ngram_size
        text_maker.input_text(text_easy_deterministic)

        outputs[text_maker.NICKNAME] = text_maker.make_sentences(1)

    # expected is that all text makers output same deterministic sentence for these inputs.
    # we can check that pretty elegantly by stringifying, calling set, and making sure their is only 1 unique output
    # (temporary dict var is not necessary for assertion - is just for ease of debugging when something goes wrong)
    outputs_rejoined = {name: presswork.text.grammar.rejoin(output).strip() for name, output in outputs.items()}
    assert len(set(outputs_rejoined.values())) == 1


def _test_self_ensure_test_would_fail_if_comparison_was_invalid(generated_tokens, input_tokenized):
    """ for posterity, let's add a self-check to make sure failure WOULD happen when it should.

    given comparison test has already passed - generate_tokens *ARE* subset of input_tokenized -
    then we can take those valid args, and invalidate them, by throwing erroneous token onto generated_tokens.
    this should fail, confirming test would fail if something was off.
    """
    invalid_word_set_comparison = helpers.WordSetComparison(
            generated_tokens=generated_tokens + ["XXXXXXXXXXXX_Not_In_Input" * 20],
            input_tokenized=input_tokenized,
            quiet=True)
    assert not invalid_word_set_comparison.output_is_subset_of_input
    return True


# ------------------------------------------------------------------------------------------------
# Following tests are more about avoiding usage issues (more than properties of the text making)
# ================================================================================================
def test_locked_after_input_text(each_text_maker):
    text_maker = each_text_maker
    text_maker.input_text("Foo bar baz. Foo bar quux.")

    with pytest.raises(text_makers.TextMakerIsLockedException):
        text_maker.input_text("This should not be loaded")

    output = text_maker.make_sentences(50)

    assert "This" not in presswork.text.grammar.rejoin(output)
    assert "loaded" not in presswork.text.grammar.rejoin(output)


def test_cannot_change_ngram_size_after_inputting_text(each_text_maker):
    text_maker = each_text_maker
    text_maker.ngram_size = 4  # this is allowed, it is not locked yet...

    text_maker.input_text("Foo bar blah baz. Foo bar blah quux.")
    with pytest.raises(text_makers.TextMakerIsLockedException):
        text_maker.ngram_size = 3


def test_avoid_pollution_between_instances(each_text_maker):
    """ helps to confirm a design goal - of the instances being isolated, despite issues with underlying strategies

    two ways pollution between the instances could happen (both observed with PyMarkovChain for example):
        a) both sharing same disk persistence for the model, too automatically (now disabled)
        b) if not careful about how 2+ are set up/copied, ".strategy" could be pointer to same instance of underlying
        strategy - TextMaker.copy() added to help avoid this

    so this test case avoids regressions in (a) mainly. point (b) is helpful to this test case and normal usage,
    so might as well exercise it here
    """
    text_maker_1 = each_text_maker
    text_maker_2 = text_maker_1.clone()

    text_maker_1.input_text("Foo bar baz. Foo bar quux.")
    text_maker_2.input_text("Input text for 2 / Input text does not go to 1 / class does not share from 1")

    assert 'Foo' in str(text_maker_1.make_sentences(10))
    assert 'Foo' not in str(text_maker_2.make_sentences(10))

    assert 'Input' in str(text_maker_2.make_sentences(10))
    assert 'Input' not in str(text_maker_1.make_sentences(10))