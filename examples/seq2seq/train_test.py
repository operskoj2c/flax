# Copyright 2021 The Flax Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for flax.examples.seq2seq.train."""

import functools

from absl.testing import absltest
import jax
from jax import random
import numpy as np

from flax import optim
import train

jax.config.parse_flags_with_absl()


def create_test_optimizer():
  rng = random.PRNGKey(0)
  param = train.get_initial_params(rng)
  return optim.Adam(learning_rate=0.003).create(param)


class TrainTest(absltest.TestCase):

  def test_character_table(self):
    text = '410+19'
    enc_text = train.CTABLE.encode(text)
    dec_text = train.CTABLE.decode(enc_text)
    # The text is possibly padded with whitespace, but the trimmed output should
    # be equal to the input.
    self.assertEqual(text, dec_text.strip())

  def test_onehot(self):
    np.testing.assert_equal(
        train.onehot(np.array([0, 1, 2]), 4),
        np.array(
            [[1, 0, 0, 0],
             [0, 1, 0, 0],
             [0, 0, 1, 0]],
            dtype=np.float32)
    )
    np.testing.assert_equal(
        jax.vmap(functools.partial(train.onehot, vocab_size=4))(
            np.array([[0, 1], [2, 3]])),
        np.array(
            [[[1, 0, 0, 0],
              [0, 1, 0, 0]],
             [[0, 0, 1, 0],
              [0, 0, 0, 1]]],
            dtype=np.float32)
    )

  def test_mask_sequences(self):
    np.testing.assert_equal(
        train.mask_sequences(
            np.arange(1, 13).reshape((4, 3)),
            np.array([3, 2, 1, 0])
        ),
        np.array(
            [[1, 2, 3],
             [4, 5, 0],
             [7, 0, 0],
             [0, 0, 0]]
        )
    )

  def test_train_one_step(self):
    batch, masks = train.get_batch(128)

    optimizer = create_test_optimizer()
    key = random.PRNGKey(0)
    _, train_metrics = train.train_step(optimizer, batch, masks, key)

    self.assertLessEqual(train_metrics['loss'], 5)
    self.assertGreaterEqual(train_metrics['accuracy'], 0)

  def test_decode_batch(self):
    key = random.PRNGKey(0)
    optimizer = create_test_optimizer()
    batch, masks = train.get_batch(5)
    train.decode_batch(optimizer.target, batch, masks, key)

if __name__ == '__main__':
  absltest.main()
