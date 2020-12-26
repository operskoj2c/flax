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

"""Early stopping."""

from flax import struct


@struct.dataclass
class EarlyStopping:
  """Early stopping to avoid overfitting during training.
  
  Attributes:
    min_delta: Minimum delta between updates to be considered an
        improvement.
    patience: Number of steps of no improvement before stopping.
    best_metric: Current best metric value.
    patience_count: Number of steps since last improving update.
    should_stop: Whether the training loop should stop to avoid 
        overfitting.
  """
  min_delta: float = 0
  patience: int = 0
  best_metric: float = None
  patience_count: int = 0
  should_stop: bool = False

  def reset(self):
    return self.replace(min_delta=self.min_delta,
                        patience=self.patience,
                        best_metric=None,
                        patience_count=0,
                        should_stop=False)

  def update(self, metric):
    """Update the state based on metric.
    
    Returns:
      Whether there was an improvement greater than min_delta from
          the previous best_metric and the updated EarlyStop object.
    """

    if self.best_metric is None or self.best_metric - metric > self.min_delta:
      return True, self.replace(min_delta=self.min_delta,
                                patience=self.patience,
                                best_metric=metric,
                                patience_count=0,
                                should_stop=self.should_stop)
    else:
      should_stop = self.patience_count >= self.patience or self.should_stop
      return False, self.replace(min_delta=self.min_delta,
                                patience=self.patience,
                                best_metric=self.best_metric,
                                patience_count=self.patience_count + 1,
                                should_stop=should_stop)
