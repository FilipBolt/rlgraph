# Copyright 2018/2019 The RLgraph authors. All Rights Reserved.
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
# ==============================================================================

from math import log

from rlgraph import get_backend
from rlgraph.components.action_adapters import ActionAdapter
from rlgraph.utils.decorators import graph_fn
from rlgraph.utils.ops import DataOpTuple
from rlgraph.utils.util import SMALL_NUMBER

if get_backend() == "tf":
    import tensorflow as tf
elif get_backend() == "pytorch":
    import torch


class BetaDistributionAdapter(ActionAdapter):
    """
    Action adapter for the Beta distribution
    """
    def get_units_and_shape(self):
        units = 2 * self.action_space.flat_dim  # Those two dimensions are the mean and log sd
        # Add moments (2x for each action item).
        if self.action_space.shape == ():
            new_shape = (2,)
        else:
            new_shape = tuple(list(self.action_space.shape[:-1]) + [self.action_space.shape[-1] * 2])
        return units, new_shape

    @graph_fn
    def _graph_fn_get_parameters_from_adapter_outputs(self, adapter_outputs):
        parameters = None

        full_action_space_rank = len(self.action_space.get_shape(with_batch_rank=True, with_time_rank=True))

        if get_backend() == "tf":
            # Stabilize both alpha and beta (currently together in last_nn_layer_output).
            parameters = tf.clip_by_value(
                adapter_outputs, clip_value_min=log(SMALL_NUMBER), clip_value_max=-log(SMALL_NUMBER)
            )
            parameters = tf.math.log((tf.exp(parameters) + 1.0)) + 1.0
            alpha, beta = tf.split(parameters, num_or_size_splits=2, axis=-1)

            # If action_space is 0D, we have to squeeze the params by 1 dim to make them match our action_space.
            if full_action_space_rank != len(alpha.shape.as_list()):
                # Assume a difference by exactly 1 dim.
                assert len(alpha.shape.as_list()) == full_action_space_rank + 1
                alpha = tf.squeeze(alpha, axis=-1)
                beta = tf.squeeze(beta, axis=-1)

            alpha._batch_rank = 0
            beta._batch_rank = 0

            parameters = DataOpTuple([alpha, beta])

        elif get_backend() == "pytorch":
            # Stabilize both alpha and beta (currently together in last_nn_layer_output).
            parameters = torch.clamp(
                adapter_outputs, min=log(SMALL_NUMBER), max=-log(SMALL_NUMBER)
            )
            parameters = torch.log((torch.exp(parameters) + 1.0)) + 1.0

            # Split in the middle.
            alpha, beta = torch.split(parameters, split_size_or_sections=int(parameters.shape[0] / 2), dim=-1)

            # If action_space is 0D, we have to squeeze the params by 1 dim to make them match our action_space.
            if full_action_space_rank != len(list(alpha.size)):
                # Assume a difference by exactly 1 dim.
                assert len(list(alpha.size)) == full_action_space_rank + 1
                alpha = torch.squeeze(alpha, dim=-1)
                beta = torch.squeeze(beta, dim=-1)

            parameters = DataOpTuple([alpha, beta])

        return parameters, None, None
