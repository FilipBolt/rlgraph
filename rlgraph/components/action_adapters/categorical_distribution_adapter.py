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

from rlgraph import get_backend
from rlgraph.components.action_adapters import ActionAdapter
from rlgraph.spaces.space_utils import sanity_check_space
from rlgraph.utils.decorators import graph_fn
from rlgraph.utils.util import SMALL_NUMBER


if get_backend() == "tf":
    import tensorflow as tf
elif get_backend() == "pytorch":
    import torch
    from rlgraph.utils.pytorch_util import SMALL_NUMBER_TORCH


class CategoricalDistributionAdapter(ActionAdapter):
    """
    Action adapter for the Categorical distribution.
    """
    def check_input_spaces(self, input_spaces, action_space=None):
        super(CategoricalDistributionAdapter, self).check_input_spaces(input_spaces, action_space)
        # IntBoxes must have categories.
        sanity_check_space(self.action_space, must_have_categories=True)

    def get_units_and_shape(self):
        units = self.action_space.flat_dim_with_categories
        new_shape = self.action_space.get_shape(with_category_rank=True)
        return units, new_shape

    @graph_fn
    def _graph_fn_get_parameters_from_adapter_outputs(self, adapter_outputs):
        """
        Returns:
            Tuple:
                - DataOp: Raw logits (parameters for a Categorical Distribution).
                - DataOp: log-probs: log(softmaxed_logits).
        """
        parameters = adapter_outputs
        probs = None
        log_probs = None

        if get_backend() == "tf":
            parameters._batch_rank = 0
            # Probs (softmax).
            probs = tf.maximum(x=tf.nn.softmax(logits=parameters, axis=-1), y=SMALL_NUMBER)
            probs._batch_rank = 0
            # Log probs.
            log_probs = tf.math.log(x=probs)
            log_probs._batch_rank = 0

        elif get_backend() == "pytorch":
            # Probs (softmax).
            probs = torch.max(torch.softmax(parameters, dim=-1), SMALL_NUMBER_TORCH)
            # Log probs.
            log_probs = torch.log(probs)

        return parameters, probs, log_probs
