# Copyright 2020 The Flax Authors.
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

"""Benchmark for the ImageNet example using fake data for quick perf results."""
import pathlib
import time

from absl import flags
from absl.testing import absltest
from absl.testing.flagsaver import flagsaver
import imagenet_main
from flax.testing import Benchmark
import jax

import tensorflow_datasets as tfds

# Parse absl flags test_srcdir and test_tmpdir.
jax.config.parse_flags_with_absl()
FLAGS = flags.FLAGS


class ImagenetBenchmarkFakeData(Benchmark):
  """Runs ImageNet using fake data for quickly measuring performance."""

  @flagsaver
  def test_fake_data(self):
    model_dir = self.get_tmp_model_dir()
    FLAGS.batch_size = 256 * jax.device_count()
    FLAGS.half_precision = True
    FLAGS.num_epochs = 5
    FLAGS.model_dir = model_dir

    # Go two directories up to the root of the flax directory.
    flax_root_dir = pathlib.Path(__file__).parents[2]
    data_dir = str(flax_root_dir) + '/.tfds/metadata'

    start_time = time.time()
    with tfds.testing.mock_data(num_examples=1024, data_dir=data_dir):
      imagenet_main.main([])
    benchmark_time = time.time() - start_time

    self.report_wall_time(benchmark_time)
    self.report_extras({
        'description': 'ImageNet ResNet50 with fake data',
        'model_name': 'resnet50',
        'parameters': f'hp=true,bs={FLAGS.batch_size}',
    })


if __name__ == '__main__':
  absltest.main()
