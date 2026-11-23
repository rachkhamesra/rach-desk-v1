import numpy as np
import shorts


def run(closes, rats, ma=100.0):
    C = np.array(closes, float); return shorts.retest_state(C, np.full(len(C), ma), np.array(rats, float))


def test_a_break_on_high_delivery_then_a_fall_and_a_return_is_flagged_once_it_is_back_in_the_band():
    closes = [105, 104, 99, 96, 94, 95, 97.5, 98.5, 99.5]
    rats = [1, 1, 2.0, 1, 1, 1, 1, 1, 1]
    flag, age, depth, bratio, bidx = run(closes, rats)
    assert flag.tolist() == [False] * 6 + [True, True, True]                                # 97, 98.5 and 99.5 are within 3% under the average; 96 and 94 are still too far below it
    assert int(age[-1]) == 6 and round(depth[-1], 1) == -6.0 and bratio[-1] == 2.0 and bidx[-1] == 2


def test_a_break_on_thin_delivery_does_not_count_and_neither_does_a_shallow_dip():
    assert not run([105, 104, 99, 96, 94, 95, 97, 98.5, 99.5], [1] * 9)[0].any()           # delivery was ordinary on the break
    assert not run([105, 104, 99, 98, 97.5, 98, 98.5, 99, 99.5], [1, 1, 2, 1, 1, 1, 1, 1, 1])[0].any()      # it never fell 4% under the average, so there was nothing to come back from


def test_a_reclaim_ends_the_idea_and_old_breaks_expire():
    closes = [105, 104, 99, 94, 95, 104, 99, 98, 99]                                        # back 4% over the average on day 5: reclaimed, so the later dip is not a retest of a lost level
    assert not run(closes, [1, 1, 2, 1, 1, 1, 1, 1, 1])[0].any()
    long = [105, 99, 93] + [94] * 70 + [99]
    assert not run(long, [1, 2.0] + [1] * 72)[0].any()                                     # more than 60 sessions after the break
