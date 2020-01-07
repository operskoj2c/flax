# Copyright 2020 The Flax Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Input pipeline for the lm1b dataset."""

# TODO(avitalo): replace this input-pipeline with yours.

from absl import logging
import tensorflow.compat.v1 as tf
import tensorflow_datasets as tfds

tf.enable_v2_behavior()


def train_and_eval_dataset(dataset_name,
                           data_dir,
                           eval_holdout_size=0,
                           train_shuffle_files=True,
                           eval_shuffle_files=False):
  """Return train and evaluation datasets, feature info and supervised keys.

  Args:
    dataset_name: a string, the name of the dataset; if it starts with 't2t_'
      then we'll search T2T Problem registry for it, otherwise we assume it is a
      dataset from TFDS and load it from there.
    data_dir: directory where the data is located.
    eval_holdout_size: float from 0 to <1; if >0 use this much of training data
      for evaluation (instead of looking for a pre-specified VALIDATION split).
    train_shuffle_files: Boolean determining whether or not to shuffle the train
      files at startup. Set to False if you want data determinism.
    eval_shuffle_files: Boolean determining whether or not to shuffle the test
      files at startup. Set to False if you want data determinism.

  Returns:
    a 4-tuple consisting of:
     * the train tf.Dataset
     * the eval tf.Dataset
     * information about features: a python dictionary with feature names
         as keys and an object as value that provides .shape and .n_classes.
     * supervised_keys: information what's the input and what's the target,
         ie., a pair of lists with input and target feature names.
  """
  dataset_builder = tfds.builder(dataset_name, data_dir=data_dir)
  info = dataset_builder.info
  splits = dataset_builder.info.splits
  if tfds.Split.TRAIN not in splits:
    raise ValueError("To train we require a train split in the dataset.")
  train_split = tfds.Split.TRAIN
  if eval_holdout_size > 0:
    holdout_percentage = int(eval_holdout_size * 100.0)
    train_percentage = 100 - holdout_percentage
    train_split = tfds.Split.TRAIN.subsplit(tfds.percent[:train_percentage])
    eval_split = tfds.Split.TRAIN.subsplit(tfds.percent[train_percentage:])
  else:
    if tfds.Split.VALIDATION not in splits and "test" not in splits:
      raise ValueError("We require a validation or test split in the dataset.")
    eval_split = tfds.Split.VALIDATION
    if tfds.Split.VALIDATION not in splits:
      eval_split = tfds.Split.TEST
  train = tfds.load(
      name=dataset_name,
      split=train_split,
      data_dir=data_dir,
      shuffle_files=train_shuffle_files)
  valid = tfds.load(
      name=dataset_name,
      split=eval_split,
      data_dir=data_dir,
      shuffle_files=eval_shuffle_files)
  keys = None
  if info.supervised_keys:
    keys = ([info.supervised_keys[0]], [info.supervised_keys[1]])
  return train, valid, info.features, keys


def _batch_fun(dataset,
               training,
               shapes,
               n_devices,
               batch_size_per_device=32,
               batch_size=None,
               eval_batch_size=32,
               bucket_length=32,
               buckets=None,
               buckets_include_inputs_in_length=False,
               max_eval_length=None):
  """Batching function."""
  # Batch size is batch_size_per_device * n_devices unless given directly.
  batch_size = batch_size or batch_size_per_device * n_devices
  # If bucketing is not specified, check if target shapes are variable.
  cur_batch_size = batch_size if training else eval_batch_size
  # Make cur_batch_size divisible by n_devices.
  cur_batch_size = max(cur_batch_size // n_devices, 1) * n_devices
  # Create heuristic buckets is none are specified.
  if buckets is None:
    variable_target_shapes = False
    target_shape = shapes[1]
    for dim in target_shape:
      if dim is None:
        variable_target_shapes = True
    logging.info(
        "Heuristically setting bucketing to %s based on shapes "
        "of target tensors.", variable_target_shapes)
    if variable_target_shapes:
      bucket_boundaries = [
          bucket_length // 4, bucket_length // 2, bucket_length,
          bucket_length * 2, bucket_length * 4, bucket_length * 8,
          bucket_length * 16
      ]
      if not training:
        max_eval_length = max_eval_length or bucket_length * 32
        bucket_boundaries[-1] = max_eval_length
      # We will pad to boundaries which pads to bucket_boundary - 1: add 1 here.
      bucket_boundaries = [b + 1 for b in bucket_boundaries]
      bucket_batch_sizes = [
          cur_batch_size * 4, cur_batch_size * 2, cur_batch_size,
          cur_batch_size // 2, cur_batch_size // 4, cur_batch_size // 8,
          cur_batch_size // 16, 1
      ]
      if not training:
        bucket_batch_sizes[-2] = cur_batch_size // max_eval_length
      # Make batch sizes divisible by n_devices.
      bucket_batch_sizes = [
          max(b // n_devices, 1) * n_devices for b in bucket_batch_sizes
      ]
      buckets = (bucket_boundaries, bucket_batch_sizes)

  if buckets:
    logging.info("Bucketing with buckets %s.", str(buckets))

    def example_length(example_inputs, target):
      """The length function used by bucket_by_sequence_length to bucket."""
      other_length = 0
      if buckets_include_inputs_in_length:
        other_length = tf.shape(example_inputs["inputs"])[0]
      return tf.maximum(tf.shape(target)[0], other_length)

    boundaries, batch_sizes = buckets
    dataset = dataset.apply(
        tf.data.experimental.bucket_by_sequence_length(
            example_length,
            boundaries,
            batch_sizes,
            pad_to_bucket_boundary=True))
  else:
    dataset = dataset.padded_batch(cur_batch_size, shapes)
  return dataset


def _lm1b_preprocess(dataset,
                     training,
                     max_target_length=512,
                     max_eval_target_length=2048):
  """Preprocessing for lm1b dataset.

  Args:
    dataset: tfds dataset.
    training: bool, if training.
    max_target_length: max train target length
    max_eval_target_length: maximum eval target length

  Returns:
   Preprocessed dataset.
  """

  def target_right_length(target):
    return tf.less(tf.shape(target["text"])[0], max_target_length + 1)

  def eval_target_right_length(target):
    return tf.less(tf.shape(target["text"])[0], max_eval_target_length + 1)

  if max_target_length > 0 and training:
    dataset = dataset.filter(target_right_length)
  if max_eval_target_length > 0 and not training:
    dataset = dataset.filter(eval_target_right_length)
  return dataset


def _shuffle_and_batch_lm1b_data(dataset,
                                 target_names,
                                 features_info,
                                 training,
                                 n_devices,
                                 shuffle_buffer_size=1024,
                                 max_target_length=512,
                                 max_eval_target_length=2048,
                                 batch_size_per_device=32,
                                 buckets=None):
  """Shuffle and batch the given dataset."""

  def append_targets(example):
    """Append targets to the example dictionary. Needed for Keras."""
    if len(target_names) == 1:
      return (example, example[target_names[0]])
    targets = {}
    for name in target_names:
      targets[name] = example[name]
    return (example, targets)

  dataset = _lm1b_preprocess(
      dataset,
      training,
      max_target_length=max_target_length,
      max_eval_target_length=max_eval_target_length)
  dataset = dataset.map(append_targets)
  if training:
    dataset = dataset.shuffle(shuffle_buffer_size)
    dataset = dataset.repeat()
  shapes = {k: features_info[k].shape for k in features_info}
  shapes = (shapes, shapes[target_names[0]])
  dataset = _batch_fun(
      dataset,
      training,
      shapes,
      n_devices,
      batch_size_per_device=batch_size_per_device,
      max_eval_length=max_eval_target_length,
      buckets=buckets)
  return dataset


def get_lm1b_datasets(n_devices,
                      batch_size_per_device=32,
                      dynamic_batching=True,
                      max_target_length=512,
                      max_eval_target_length=2048):
  """Load and return dataset of batched examples for use during training."""
  (train_data, eval_data, features_info, keys) = train_and_eval_dataset(
      "lm1b/subwords32k",
      None,
      train_shuffle_files=True,
      eval_shuffle_files=False)

  if dynamic_batching:
    train_buckets = None
    eval_buckets = None

  else:
    # buckets should be (bucket_boundaries, bucket_batch_sizes)
    train_buckets = ([max_target_length + 1],
                     [n_devices * batch_size_per_device, 1])
    eval_buckets = ([max_eval_target_length + 1],
                    [n_devices * batch_size_per_device, 1])

  _, target_names = keys[0], keys[1]
  train_batches = _shuffle_and_batch_lm1b_data(
      train_data,
      target_names,
      features_info,
      training=True,
      n_devices=n_devices,
      batch_size_per_device=batch_size_per_device,
      buckets=train_buckets)

  eval_batches = _shuffle_and_batch_lm1b_data(
      eval_data,
      target_names,
      features_info,
      training=False,
      n_devices=n_devices,
      batch_size_per_device=batch_size_per_device,
      buckets=eval_buckets)

  return train_batches.prefetch(2), eval_batches.prefetch(2), features_info
