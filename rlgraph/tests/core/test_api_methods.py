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

from __future__ import absolute_import, division, print_function

import logging
import unittest

import mock
from tensorflow.core.framework import summary_pb2

from rlgraph.tests import ComponentTest
from rlgraph.tests.test_util import regex_pattern
from rlgraph.utils import root_logger
from rlgraph.tests.dummy_components import *
from rlgraph.tests.dummy_components_with_sub_components import *


class TestAPIMethods(unittest.TestCase):
    """
    Tests for different ways to place and then connect two or more sub-Components into the root-Component.
    Tests different ways of defining these connections using API-methods.
    """
    root_logger.setLevel(level=logging.INFO)

    def test_component_with_sub_component(self):
        a = DummyWithSubComponents(scope="A")
        test = ComponentTest(component=a, input_spaces=dict(input_=float))

        # Expected: (1): in + 2.0  (2): [result of (1)] + 1.0
        test.test(("run1", 1.1), expected_outputs=[3.1, 4.1], decimals=4)
        # Expected: in - 2.0 + 1.0
        test.test(("run2", 1.1), expected_outputs=0.1, decimals=4)

    def test_connecting_two_1to1_components(self):
        """
        Adds two components with 1-to-1 graph_fns to the core, connects them and passes a value through it.
        """
        core = Component(scope="container")
        sub_comp1 = Dummy1To1(scope="comp1")
        sub_comp2 = Dummy1To1(scope="comp2")
        core.add_components(sub_comp1, sub_comp2)

        @rlgraph_api(component=core)
        def run(self_, input_):
            out = sub_comp1.run(input_)
            return sub_comp2.run(out)

        test = ComponentTest(component=core, input_spaces=dict(input_=float))

        # Expected output: input + 1.0 + 1.0
        test.test(("run", 1.1), expected_outputs=3.1)
        test.test(("run", -5.1), expected_outputs=-3.1)

    def test_connecting_1to2_to_2to1(self):
        """
        Adds two components with 1-to-2 and 2-to-1 graph_fns to the core, connects them and passes a value through it.
        """
        core = Component(scope="container")
        sub_comp1 = Dummy1To2(scope="comp1")  # outs=in,in+1
        sub_comp2 = Dummy2To1(scope="comp2")  # out =in1+in2
        core.add_components(sub_comp1, sub_comp2)

        @rlgraph_api(component=core)
        def run(self_, input_):
            out1, out2 = sub_comp1.run(input_)
            return sub_comp2.run(out1, out2)

        test = ComponentTest(component=core, input_spaces=dict(input_=float))

        # Expected output: input + (input + 1.0)
        test.test(("run", 100.9), expected_outputs=np.float32(202.8))
        test.test(("run", -5.1), expected_outputs=np.float32(-9.2))

    def test_1to1_to_2to1_component_with_constant_input_value(self):
        """
        Adds two components in sequence, 1-to-1 and 2-to-1, to the core and blocks one of the api_methods of 2-to-1
        with a constant value (so that this constant value is not at the border of the root-component).
        """
        core = Component(scope="container")
        sub_comp1 = Dummy1To1(scope="A")
        sub_comp2 = Dummy2To1(scope="B")
        core.add_components(sub_comp1, sub_comp2)

        @rlgraph_api(component=core)
        def run(self_, input_):
            out = sub_comp1.run(input_)
            return sub_comp2.run(out, 1.1)

        test = ComponentTest(component=core, input_spaces=dict(input_=float))

        # Expected output: (input + 1.0) + 1.1
        test.test(("run", 78.4), expected_outputs=80.5)
        test.test(("run", -5.2), expected_outputs=-3.1)

    def test_diamond_4x_sub_component_setup(self):
        """
        Adds 4 sub-components (A, B, C, D) with 1-to-1 graph_fns to the core.
        in1 -> A (like preprocessor in DQN)
        in2 -> A
        A -> B (like policy in DQN)
        A -> C (like target policy in DQN)
        B -> Din1 (like loss func in DQN: q_vals_s)
        C -> Din2 (q_vals_sp)
        """
        container = Component(scope="container")
        a = Dummy1To1(scope="A")
        b = Dummy1To1(scope="B")
        c = Dummy1To1(scope="C")
        d = Dummy2To1(scope="D")

        # Throw in the sub-components.
        container.add_components(a, b, c, d)

        # Define container's API:
        @rlgraph_api(name="run", component=container)
        def container_run(self_, input1, input2):
            """
            Describes the diamond setup in1->A->B; in2->A->C; C,B->D->output
            """
            # Adds constant value 1.0  to 1.1 -> 2.1
            in1_past_a = self_.sub_components["A"].run(input1)
            # 0.5 + 1.0 = 1.5
            in2_past_a = self_.sub_components["A"].run(input2)
            # 2.1 + 1.0 = 3.1
            past_b = self_.sub_components["B"].run(in1_past_a)
            # 1.5 + 1.0 = 2.5
            past_c = self_.sub_components["C"].run(in2_past_a)
            # 3.1 + 2.5 = 5.6
            past_d = self_.sub_components["D"].run(past_b, past_c)
            return past_d

        test = ComponentTest(component=container, input_spaces=dict(input1=float, input2=float))

        # Push both api_methods through graph to receive correct (single-op) output calculation.
        test.test(("run", [1.1, 0.5]), expected_outputs=5.6)

    def test_calling_sub_components_api_from_within_graph_fn(self):
        a = DummyCallingSubComponentsAPIFromWithinGraphFn(scope="A")
        test = ComponentTest(component=a, input_spaces=dict(input_=float))

        # Expected: (1): 2*in + 10
        test.test(("run", 1.1), expected_outputs=12.2, decimals=4)

    def test_component_that_defines_custom_api_methods(self):
        a = DummyThatDefinesCustomAPIMethod()

        test = ComponentTest(component=a, input_spaces=dict(input_=float))

        test.test(("some_custom_api_method", 1.23456), expected_outputs=1.23456, decimals=5)

    def test_call_in_comprehension(self):
        """
        Tests calling graph functions within list comprehensions.

        https://github.com/rlgraph/rlgraph/issues/41
        """
        container = Component(scope="container")
        sub_comps = [Dummy1To1(scope="dummy-{}".format(i)) for i in range(3)]
        container.add_components(*sub_comps)

        # Define container's API:
        @rlgraph_api(name="test", component=container)
        def container_test(self_, input_):
            # results = []
            # for i in range(len(sub_comps)):
            #     results.append(sub_comps[i].run(input_))
            results = [x.run(input_) for x in sub_comps]
            return self_._graph_fn_sum(*results)

        @graph_fn(component=container)
        def _graph_fn_sum(self_, *inputs):
            return sum(inputs)

        test = ComponentTest(component=container, input_spaces=dict(input_=float))
        test.test(("test", 1.23), expected_outputs=len(sub_comps) * (1.23 + 1), decimals=2)

    def test_providing_method_as_argument(self):
        component = DummyWithVar()
        test = ComponentTest(component=component, input_spaces=dict(input_=float))

        test.test((component.run_plus, 1.23456), expected_outputs=3.23456, decimals=5)
        test.test((component.run_minus, 1.23456), expected_outputs=-0.7654, decimals=4)

    @staticmethod
    def _parse_summary_if_needed(summary):
        """
        Parses the summary if it is provided in serialized form (bytes).
        This code is copied from tensorflow's SummaryToEventTransformer::add_summary
        :param summary:
        :return:
        """
        if isinstance(summary, bytes):
            summ = summary_pb2.Summary()
            summ.ParseFromString(summary)
            summary = summ
        return summary

    def test_summaries(self):
        container = Component(scope="container")

        # Define container's API:
        @rlgraph_api(component=container)
        def add(self_, value, value2):
            return self_._graph_fn_sum(value, value2)

        @graph_fn(component=container)
        def _graph_fn_sum(self_, *inputs):
            summary_op = tf.compat.v1.summary.histogram("summary_sum", inputs)
            self_.register_summary_op(summary_op)
            return sum(inputs)

        @rlgraph_api(component=container)
        def _graph_fn_graph_api(self_):
            summary_op = tf.compat.v1.summary.scalar("summary_graph_api", 1.0)
            self_.register_summary_op(summary_op)
            return tf.constant(1.0)

        @rlgraph_api(component=container)
        def api_method_double(self_, value):
            return self_.add(value, value)

        @rlgraph_api(component=container)
        def _graph_fn_api_method_complex(self_, value):
            doubled = self_._graph_fn_sum(value, value)
            incremented = self_._graph_fn_inc(doubled)
            denominator = self_.graph_api()
            return incremented / denominator

        @rlgraph_api(component=container)
        def increment(self_, value):
            return self_._graph_fn_inc(value)

        test = ComponentTest(component=container, input_spaces=dict(
            value=float,
            value2=float
        ), auto_build=False)

        @graph_fn(component=container)
        def _graph_fn_inc(self_, value):
            summary_op = tf.compat.v1.summary.scalar("summary_inc", value)
            self_.register_summary_op(summary_op)
            assign_op = tf.compat.v1.assign_add(test.graph_executor.global_training_timestep, 1)
            with tf.control_dependencies([assign_op]):
                return value + 1

        test.build()

        test.graph_executor.summary_writer = mock.Mock(
            spec=test.graph_executor.summary_writer,
            wraps=test.graph_executor.summary_writer
        )
        test.graph_executor.summary_writer.add_summary = mock.Mock()

        test.test((add, [1.0, 2.0]), expected_outputs=3.0, decimals=2)
        assert test.graph_executor.summary_writer.add_summary.call_count == 1
        summary, step = test.graph_executor.summary_writer.add_summary.call_args[0]
        summary = self._parse_summary_if_needed(summary)
        assert len(summary.value) == 1
        assert summary.value[0].tag == regex_pattern(container.scope + "/summary_sum" + r"(_\d)?")
        assert step == 0

        test.graph_executor.summary_writer.add_summary.reset_mock()
        test.test((increment, [6.0]), expected_outputs=7.0, decimals=2)
        assert test.graph_executor.summary_writer.add_summary.call_count == 1
        summary, step = test.graph_executor.summary_writer.add_summary.call_args[0]
        summary = self._parse_summary_if_needed(summary)
        assert len(summary.value) == 1
        assert summary.value[0].tag == container.scope + "/summary_inc"
        assert step == 1

        test.graph_executor.summary_writer.add_summary.reset_mock()
        test.test("graph_api", expected_outputs=1.0, decimals=2)
        assert test.graph_executor.summary_writer.add_summary.call_count == 1
        summary, step = test.graph_executor.summary_writer.add_summary.call_args[0]
        summary = self._parse_summary_if_needed(summary)
        assert len(summary.value) == 1
        assert summary.value[0].tag == container.scope + "/summary_graph_api"
        assert step == 1

        test.graph_executor.summary_writer.add_summary.reset_mock()
        test.test((api_method_double, [3.0]), expected_outputs=6.0, decimals=2)
        assert test.graph_executor.summary_writer.add_summary.call_count == 1
        summary, step = test.graph_executor.summary_writer.add_summary.call_args[0]
        summary = self._parse_summary_if_needed(summary)
        assert len(summary.value) == 1
        assert summary.value[0].tag == regex_pattern(container.scope + "/summary_sum" + r"(_\d)?")
        assert step == 1

        test.graph_executor.summary_writer.add_summary.reset_mock()
        test.test(("api_method_complex", [3.0]), expected_outputs=7.0, decimals=2)
        assert test.graph_executor.summary_writer.add_summary.call_count == 1
        summary, step = test.graph_executor.summary_writer.add_summary.call_args[0]
        summary = self._parse_summary_if_needed(summary)
        assert len(summary.value) == 3
        assert summary.value[0].tag == regex_pattern(container.scope + "/summary_sum" + r"(_\d)?")
        assert summary.value[1].tag == regex_pattern(container.scope + "/summary_inc" + r"(_\d)?")
        assert summary.value[2].tag == regex_pattern(container.scope + "/summary_graph_api" + r"(_\d)?")
        assert step == 2


    #def test_kwargs_in_api_call(self):
    #    core = Component(scope="container")
    #    sub_comp = Dummy2To2(scope="comp1")
    #    core.add_components(sub_comp)

    #    @api(component=core)
    #    def run(self_, input1=1.0, input2=2.0):
    #        return sub_comp.run(input1, input2)

    #    test = ComponentTest(component=core, input_spaces=dict(input1=float, input2=float))

    #    # Expected output: input + 1.0 + 1.0
    #    test.test(("run", [1.1, None]), expected_outputs=(2.1, 4.1))
    #    #test.test(("run", -5.1), expected_outputs=-3.1)

