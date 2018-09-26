from __future__ import division
from .elemnts.ste import S_T_E, PackedIntervalSet, PackedInput
from .elemnts.element import StartType, FakeRoot
from .elemnts.or_elemnt import OrElement
from .elemnts import ElementsType
import networkx as nx
import matplotlib.pyplot as plt
from collections import  deque
from tqdm import tqdm
import os
import itertools
import random
import time, operator
import math
from deap import algorithms, base, creator, tools
import numpy as np
import utility
from networkx.drawing.nx_agraph import write_dot


random.seed(a = None)



class Automatanetwork(object):
    known_attributes = {'id', 'name'}
    node_data_key = "data" # this string is used to attach node to the


    def __init__(self, id ,is_homogenous, stride):

        #TODO clean up this mechanism (has modified)
        self._has_modified = True
        self._my_graph = nx.MultiDiGraph()
        self._is_homogeneous = is_homogenous
        self.add_element(FakeRoot())  # This is not a real node. It helps for simpler striding code
        self._stride = stride
        #TODO refactor to automata id
        self._id = id
        #TODO cleanup, _last_index?
        self.last_assigned_id = 0

    def _clear_mark_idx(self):
        for node in self.nodes:
            node.mark_index = -1


    def get_new_id(self):
        self.last_assigned_id += 1
        assert not self.last_assigned_id in self._my_graph.nodes
        return self.last_assigned_id

    @classmethod
    # this function is used in connecteed components detection
    def _from_graph(cls, id ,is_homogenous, graph ,stride, last_assigned_id):
        assert is_homogenous, "graph should be in homogenous state"

        automata = Automatanetwork(id = id,is_homogenous = True, stride = stride)
        automata.last_assigned_id = last_assigned_id
        del automata._my_graph
        automata._my_graph = graph
        automata.add_element(FakeRoot())

        for node in graph.nodes:
            if node.start_type == StartType.all_input or \
                            node.start_type == StartType.start_of_data:
                automata.add_edge(automata.fake_root, node)
        return automata


    @property
    def fake_root(self):
        return self._my_graph.nodes[FakeRoot.fake_root_id][Automatanetwork.node_data_key]

    @property
    def nodes(self):
        return self._my_graph.nodes



    @classmethod
    def from_xml(cls, xml_node):

        Automatanetwork._check_validity(xml_node)

        #TODO xml files are always homogeneous
        graph_ins = Automatanetwork(id=xml_node.attrib['id'], is_homogenous=True, stride=1)

        original_id_to_node = {}


        for child in xml_node:
            if child.tag == 'state-transition-element':
                ste = S_T_E.from_xml_node(child, graph_ins.get_new_id())
                original_id_to_node[ste.original_id] = ste
                graph_ins.add_element(ste)
            elif child.tag == 'or':
                or_gate = OrElement.from_xml_node(child, graph_ins.get_new_id())
                original_id_to_node[or_gate.original_id] = or_gate
                graph_ins.add_element(to_add_element=or_gate, connect_to_fake_root= False)
            elif child.tag == 'description': # not important
                continue
            else:
                raise RuntimeError('unsupported child of automata-network-> ' + child.tag )

        for node in graph_ins.nodes:
            if node.type == ElementsType.FAKE_ROOT:
                continue
            for dst_ids in node.get_adjacency_list():
                dst_node = original_id_to_node[dst_ids]
                graph_ins.add_edge(node, dst_node)

            node.delete_adjacency_list()

        return graph_ins

    @property
    def stride_value(self):
        return self._stride


    @property
    def edges(self):
        return self._my_graph.edges

    def get_filtered_nodes(self,lambda_func):
        return (n for n in self.nodes if lambda_func(n))


    @staticmethod
    def _check_validity(xml_node):
        attr_set = set(xml_node.attrib)
        assert attr_set.issubset(Automatanetwork.known_attributes)

    #TODO Should not this be private _
    def unmark_all_nodes(self):
        for n in self.nodes:
            n.marked = False

    def add_element(self, to_add_element, connect_to_fake_root = True):

        """
        :param to_add_element: Add a ste to the graph
        :return:
        """
        assert to_add_element.id not in self.nodes
        self._my_graph.add_node(to_add_element,
                                **{ Automatanetwork.node_data_key :to_add_element})
        self._has_modified = True
        #TODO is it necessary to be homogeneous
        if self.is_homogeneous and to_add_element.is_start() and connect_to_fake_root: # only for homogenous graphs
            self.add_edge(self.fake_root, to_add_element) # add an esge from fake root to all start nodes


    def get_STE_by_id(self, id):
        """
        this function returns the STE instance using the id
        :param id: id of the ste
        :return:
        """
        return self.nodes[id][Automatanetwork.node_data_key]


    @property
    def nodes_count(self):
        return len(self._my_graph) -1 # fake_root is not counted

    #TODO make this a poperty
    def get_number_of_edges(self):
        return self._my_graph.number_of_edges() - self.number_of_start_nodes

    def get_average_intervals(self):

        intervals_sum = 0
        for node in self.nodes:
            if node.start_type == StartType.fake_root:
                continue
            intervals_sum += len(node.symbols)

        return intervals_sum / self.nodes_count

    def add_edge(self, src, dest,**kwargs):
        if self.is_homogeneous:
            assert not self._my_graph.has_edge(src, dest)
        if not 'label' in kwargs and dest.type==ElementsType.STE:
            kwargs['label'] = dest.symbols
        if not 'start_type' in kwargs:
            kwargs['start_type'] = dest.start_type

        self._my_graph.add_edge(src,dest,**kwargs)
        self._has_modified = True
        return

        if self.is_homogeneous:
            if self._my_graph.has_edge(src, dest):
                return
            else:
                self._my_graph.add_edge(src, dest, **kwargs)
                self._has_modified = True
        else:
            if self._my_graph.has_edge(src, dest):
                edge_data = self._my_graph.get_edge_data(src, dest, key=False)
                if edge_data['start_type'] == kwargs['start_type']:
                    for intvl in kwargs['label']:
                        edge_data['label'].add_interval(intvl)
                else:
                    self._my_graph.add_edge(src, dest, **kwargs)
                    self._has_modified = True

            else:
                self._my_graph.add_edge(src, dest, **kwargs)
                self._has_modified = True





    def get_single_stride_graph(self):
        """
        This function make a new graph with single stride
        It assumes that the graph in current state is a homogeneous graph
        :return: a graph with a single step stride
        """
        assert not self.does_have_all_input(), "Automata should not have all-input nodes"
        dq = deque()
        self.unmark_all_nodes()
        strided_graph = Automatanetwork(id = self._id + "_S1",is_homogenous= False, stride= self.stride_value*2)
        self.fake_root.marked = True
        ###
        dq.appendleft(self.fake_root)
        residual_STEs_dic = {}
        new_STEs_dic = {self.fake_root.id:strided_graph.fake_root}
        star_symbol_set = PackedIntervalSet.get_star(self.stride_value)

        while dq:

            current_ste = dq.pop()


            for l1_neighb_idx, l1_neigh in enumerate(self._my_graph.neighbors(current_ste)):
                if l1_neigh.report:

                    if l1_neigh.id not in residual_STEs_dic:
                        new_id = strided_graph.get_new_id()

                        semi_final_ste = S_T_E(start_type=StartType.unknown, is_report=True,
                                           is_marked=False, id= new_id,
                                           symbol_set=None, adjacent_S_T_E_s= None ,report_residual =
                                               self.stride_value if l1_neigh.report_residual == 0
                                               else l1_neigh.report_residual,
                                               report_code= l1_neigh.report_code)
                        strided_graph.add_element(semi_final_ste)
                        residual_STEs_dic[l1_neigh.id] = semi_final_ste


                    if self.is_homogeneous: # homogeneous case
                        strided_graph.add_edge(new_STEs_dic[current_ste.id],
                                               residual_STEs_dic[l1_neigh.id],
                                               label=PackedIntervalSet.combine(l1_neigh.symbols, star_symbol_set),
                                               start_type=l1_neigh.start_type
                                               if current_ste.start_type == StartType.fake_root else
                                               StartType.non_start)
                    else: # non homogeneous case
                        l1_edges = self._my_graph.out_edges(current_ste, data=True, keys=False)
                        #TODO Is there any API in networkx for getting these esdges directly
                        l1_edges = filter(lambda x: x[1] == l1_neigh, l1_edges)
                        for l1_edge in l1_edges:
                            strided_graph.add_edge(new_STEs_dic[current_ste.id],
                                                   residual_STEs_dic[l1_neigh.id],
                                                   label=PackedIntervalSet.combine(l1_edge[2]['label'],
                                                                                   star_symbol_set),
                                                   start_type=l1_edge[2]['start_type'] if
                                                   current_ste.start_type == StartType.fake_root
                                                   else StartType.non_start)

                for l2_neighb_idx, l2_neigh in enumerate(self._my_graph.neighbors(l1_neigh)):
                    #print len(dq), l1_neighb_idx, l2_neighb_idx
                    if not l2_neigh.marked:
                        is_report = l2_neigh.report
                        new_id = strided_graph.get_new_id()
                        report_res = -1
                        if is_report:
                            report_res = 0 if l2_neigh.report_residual == 0 else \
                                self.stride_value + l2_neigh.report_residual
                        temp_ste = S_T_E(start_type = StartType.unknown, is_report= is_report,
                                                    is_marked=False, id = new_id, symbol_set= None,
                                         adjacent_S_T_E_s=None, report_residual =report_res,
                                         report_code = l2_neigh.report_code)
                        strided_graph.add_element(temp_ste)
                        new_STEs_dic[l2_neigh.id] = temp_ste
                        l2_neigh.marked = True
                        dq.appendleft(l2_neigh)

                    if self.is_homogeneous: # for homogeneous case
                        strided_graph.add_edge(new_STEs_dic[current_ste.id], new_STEs_dic[l2_neigh.id],
                                               label= PackedIntervalSet.combine(l1_neigh.symbols, l2_neigh.symbols),
                                           start_type = l1_neigh.start_type
                                           if current_ste.start_type == StartType.fake_root else StartType.non_start)
                    else: # non homogeneous case
                        l1_edges = self._my_graph.out_edges(current_ste, data = True, keys = False)
                        l1_edges = filter(lambda x: x[1] == l1_neigh, l1_edges)
                        l2_edges = self._my_graph.out_edges(l1_neigh, data=True, keys=False)
                        l2_edges = filter(lambda x: x[1] == l2_neigh, l2_edges)

                        for l1_edge in l1_edges:
                            for l2_edge in l2_edges:
                                strided_graph.add_edge(new_STEs_dic[current_ste.id], new_STEs_dic[l2_neigh.id],
                                                       label=PackedIntervalSet.combine(l1_edge[2]['label'],
                                                                                       l2_edge[2]['label']),
                                                       start_type=l1_edge[2]['start_type']
                                                       if current_ste.start_type == StartType.fake_root
                                                       else StartType.non_start)

        return strided_graph

    def _refine_edges(self):
        """
        this function removes the redundant edges
        :return:
        """
        #TODO implement this
        assert not self.is_homogeneous(), "this function has been targeted for non homogeneous automatas"
        pass

    @property
    def number_of_start_nodes(self):
        """
        number of start nodes (fake root neighbors) in a graph
        :return:
        """
        return self._my_graph.out_degree(self.fake_root)

    @property
    def number_of_report_nodes(self):
        """
        number of report nodes in a graph
        :return:
        """
        filtered_nodes = list(self.get_filtered_nodes(lambda n: n.report))
        return len(filtered_nodes)

    def delete_node(self, node):

        #TODO log message for this operation
        assert node in self.nodes
        self._my_graph.remove_node(node)


    def _make_homogeneous_STE(self, current_ste, delete_original_ste):
        """

        :param current_ste: the STE that needs to be homogeneos
        :return:
        """

        src_dict_non_start = {}
        src_dict_all_start = {}
        src_dict_start_of_data = {}

        # src_nodes = list(self._my_graph.predecessors(current_ste))
        # edges = self._my_graph.edges(src_nodes, data = True, keys = False)
        edges = self._my_graph.in_edges(current_ste, data=True, keys=False)

        for edge in edges:

            label = edge[2]['label']
            start_type = edge[2]['start_type']

            if start_type == StartType.non_start:
                for l in label:
                    src_dict_non_start.setdefault(edge[0], PackedIntervalSet([])).add_interval(l)
            elif start_type == StartType.start_of_data:
                for l in label:
                    src_dict_start_of_data.setdefault(edge[0], PackedIntervalSet([])).add_interval(l)
            elif start_type == StartType.all_input:
                for l in label:
                    src_dict_all_start.setdefault(edge[0], PackedIntervalSet([])).add_interval(l)
            else:
                assert False  # It should not happen

        new_nodes = []
        new_all_input_nodes = self._make_homogenous_node(curr_node=current_ste, connectivity_dic=src_dict_all_start,
                                                         start_type=StartType.all_input)
        new_nodes.extend(new_all_input_nodes)

        new_start_of_data_nodes = self._make_homogenous_node(curr_node=current_ste,
                                                             connectivity_dic=src_dict_start_of_data,
                                                             start_type=StartType.start_of_data)
        new_nodes.extend(new_start_of_data_nodes)

        new_non_start_nodes = self._make_homogenous_node(curr_node=current_ste, connectivity_dic=src_dict_non_start,
                                                         start_type=StartType.non_start)
        new_nodes.extend(new_non_start_nodes)

        if current_ste in self._my_graph.neighbors(current_ste):  # handling self loop nodes

            for neighb, on_edge_char_set in src_dict_non_start.iteritems():
                if neighb == current_ste:
                    self_loop_handler = S_T_E(start_type=StartType.non_start, is_report=current_ste.report,
                                              is_marked=True, id=self.get_new_id(),
                                              symbol_set=on_edge_char_set,
                                              adjacent_S_T_E_s=None,
                                              report_residual=current_ste.report_residual,
                                              report_code=current_ste.report_code)  # self loop handlers are always non start nodes
                    self.add_element(self_loop_handler)
                    self.add_edge(self_loop_handler, self_loop_handler)
                    for node in new_nodes:
                        self.add_edge(node, self_loop_handler)

                    out_edges = self._my_graph.out_edges(current_ste, data=True, keys=False)
                    for edge in out_edges:
                        if edge[0] == edge[1]:  # self loop node
                            continue
                        self.add_edge(self_loop_handler, edge[1], label=edge[2]['label'],
                                      start_type=edge[2]['start_type'])
        if delete_original_ste:
            self.delete_node(current_ste)

    def make_homogenous(self):
        """
        :return:
        """
        self.unmark_all_nodes()
        assert not self.is_homogeneous # only works for non-homogeneous graph
        dq = deque()
        #self.fake_root.marked = True
        #dq.appendleft(self.fake_root)

        report_nodes = self.get_filtered_nodes(lambda node:node.report)
        for r_node in report_nodes:
            r_node.marked = True
            dq.append(r_node)

        while dq:
            current_ste = dq.pop()
            if current_ste.start_type == StartType.fake_root: # fake root does need processing
                continue # process next node from the queue

            for pred in self._my_graph.predecessors(current_ste):
                if not pred.marked:
                    pred.marked = True
                    dq.appendleft(pred)

            self._make_homogeneous_STE(current_ste= current_ste, delete_original_ste = True)

        self.is_homogeneous = True


    #
    # def make_homogenous(self):
    #     """
    #     :return:
    #     """
    #     self.unmark_all_nodes()
    #     assert not self.is_homogeneous # only works for non-homogeneous graph
    #     dq = deque()
    #     self.fake_root.marked = True
    #     dq.appendleft(self.fake_root)
    #
    #     while dq:
    #         current_ste = dq.pop()
    #         if current_ste.start_type == StartType.fake_root: # fake root does need processing
    #             for start_node in self._my_graph.neighbors(current_ste):
    #                 assert not start_node.marked
    #                 start_node.marked = True
    #                 dq.appendleft(start_node)
    #             continue # process next node from the queue
    #
    #         for neighb in self._my_graph.neighbors(current_ste):
    #             if not neighb.marked:
    #                 neighb.marked = True
    #                 dq.appendleft(neighb)
    #
    #         self._make_homogeneous_STE(current_ste= current_ste, delete_original_ste = True)
    #
    #     self.is_homogeneous = True

    @property
    def is_homogeneous(self):
        return self._is_homogeneous

    @is_homogeneous.setter
    def is_homogeneous(self, is_homo):
        self._is_homogeneous = is_homo

    def darw_graph_on_ax(self, draw_edge_label, ax, pos = None, color = None):
        if pos == None:
            pos = nx.spring_layout(self._my_graph, k=0.5)

        if not color:
            color = [node.get_color() for node in self.nodes]

        nx.draw(self._my_graph, pos, node_size = 100, width=0.5 , arrowsize=6, node_color=color, ax =ax)

        if draw_edge_label: # draw with edge lable
            nx.draw_networkx_edge_labels(self._my_graph, pos, node_size = 20, width = 2, arrowsize = 2,
                                         node_color= color, font_size= 1 , ax =ax)


    def draw_graph(self, file_name, draw_edge_label = False, use_dot = False, write_node_labels = True):
        """

        :param file_name: name of the png file
        :param draw_edge_label: True if writing edge labels is required
        :param use_dot: If true, uses dot method to draw the graph
        :return:
        """

        if not use_dot: # use pyplot
            ax = plt.subplot()
            self.darw_graph_on_ax(draw_edge_label , ax)
            plt.savefig(file_name, dpi=500)
            plt.close()
        else: # use dot and graphviz
            #TODO draw edge label does not work

            for node in self.nodes:
                if node.start_type == StartType.fake_root:
                    self.nodes[node.id]['color'] = 'black'
                elif node.start_type == StartType.start_of_data:
                    self.nodes[node.id]['color'] = 'green'
                elif node.start_type == StartType.all_input:
                    self.nodes[node.id]['color'] = 'greenyellow'
                elif node.report:
                    self.nodes[node.id]['color'] = 'blue'
                elif node.start_type == StartType.unknown:
                    self.nodes[node.id]['color'] = 'yellow'
                else:
                    self.nodes[node.id]['color'] = 'red'

            for edge in self._my_graph.edges(data=True,):
                edge[2]['fontsize'] = 6

            write_dot(self._my_graph, '/tmp/Rezasim_pydot.dot')
            #TODO what is this?
            if not write_node_labels:
                pass

            #TODO check return error
            os.system('dot -Tsvg /tmp/Rezasim_pydot.dot -o {}'.format(file_name))





    def get_BFS_label_dictionary(self, start_from_root = True, set_nodes_idx = True):
        """

        :param start_from_root: if set to True, first all the start nodes will be pushed. Otherwise each
        start node will be procesessed independently
        :param set_nodes_idx:
        :return:
        """
        node_to_index = {}
        last_assigned_id = -1
        self.unmark_all_nodes()
        dq = deque()
        self.fake_root.marked = True # no need to push fake root

        if set_nodes_idx:
            self._clear_mark_idx()


        for start_node in self._my_graph.neighbors(self.fake_root):
            if start_node.marked:
                continue

            assert not start_node in node_to_index, "This is a bug. Contact Reza!"
            if not start_from_root:
                last_assigned_id += 1
                node_to_index[start_node] = last_assigned_id
                if set_nodes_idx:
                    start_node.mark_index = last_assigned_id
                start_node.marked = True
                dq.appendleft(start_node)
            else:
                dq.appendleft(self.fake_root)

            while dq:
                current_node = dq.pop()
                for neighb in self._my_graph.neighbors(current_node):
                    if not neighb.marked:
                        neighb.marked = True
                        dq.appendleft(neighb)
                        last_assigned_id += 1
                        assert not neighb in node_to_index, "This is a bug. Contact Reza!"
                        node_to_index[neighb] = last_assigned_id
                        if set_nodes_idx:
                            neighb.mark_index= last_assigned_id

        return node_to_index

    def _generate_standard_index_dictionary(self):
        current_idx = 0
        out_dic = {}
        self._clear_mark_idx()

        for node in self.nodes:
            if node.start_type == StartType.fake_root:
                continue
            out_dic[node] = current_idx
            node.set_mark_idx(current_idx)
            current_idx+=1

        return  out_dic

    def get_connectivity_matrix(self, node_dictionary = None):
        if not node_dictionary:
            node_dictionary = self._generate_standard_index_dictionary()

        nodes_count = self.nodes_count
        assert nodes_count <= 256, "it only works for small automatas"
        nodes_count = 256
        switch_map = [[0 for _ in range(nodes_count)] for _ in range(nodes_count)]

        for node in node_dictionary:
            for neighb in self._my_graph.neighbors(node):
                switch_map[node_dictionary[node]][node_dictionary[neighb]] = 1

        return switch_map

    def draw_native_switch_box(self, path, node_idx_dictionary, write_cycle_in_file, **kwargs):
        assert not self.fake_root in node_idx_dictionary
        switch_map = self.get_connectivity_matrix(node_idx_dictionary)

        bounds = [0, 0.5, 1]
        utility.draw_matrix(path+".png", switch_map, bounds, **kwargs)
        if write_cycle_in_file:
            with open(path+".txt", "w") as f:
                for cycle in nx.cycle_basis(nx.Graph(self._my_graph)):
                    if self.fake_root in cycle:
                        continue
                    if len(cycle) == 1: # self loops
                        continue
                    for node in cycle:
                        f.write(str(node_idx_dictionary[node]) + "->")
                    f.write("\n")
        return switch_map

    #TODO making a generator here?
    def _generate_BFS(self):
        pass

    def add_automata(self, new_automata):
        assert self.is_homogeneous == new_automata.is_hmogeneous == True
        new_nodes_dictionary = {}
        for node in new_automata.nodes:
            if node.start_type == StartType.fake_root:
                continue

            new_node = S_T_E(start_type = node.start_type, is_report = node.report,
                             is_marked = False, id = self.get_new_id(), symbol_set= node.symbols.clone(), adjacent_S_T_E_s = [],
                             report_residual= node.report_residual, report_code=node.report_code)
            new_nodes_dictionary[node] = new_node
            self.add_element(new_node)

        for src, dst in new_automata.get_edges():
            if src.start_type == StartType.fake_root:
                continue

            self.add_edge(new_nodes_dictionary[src], new_nodes_dictionary[dst])
        return set(new_nodes_dictionary.values())


    def get_routing_cost(self, routing_template, node_dictionary):
        assert not self.fake_root in node_dictionary
        cost = 0
        for current_node in node_dictionary:
            for neighb in self._my_graph.neighbors(current_node):
                if not routing_template[node_dictionary[current_node]][node_dictionary[neighb]]:
                    cost += 1
        return cost

    def bfs_rout(self,routing_template, available_rows):
        node_dictionary = self.get_BFS_label_dictionary()
        assert not self.fake_root in node_dictionary
        cost = self.get_routing_cost(routing_template, node_dictionary)
        print "BFS cost =", cost
        return cost, node_dictionary

    #TODO this function has not been checked for the new version
    def ga_route(self, routing_template, avilable_rows):
        """
        :param routing_template:
        :param avilable_rows:
        :return:
        """
        #num_nodes  = self.get_number_of_nodes(False)
        num_nodes = len(avilable_rows)
        nodes = list(self.get_nodes())
        nodes.remove(self._fake_root)
        #node_dic = self._generate_standard_index_dictionary()
        node_dic = self.get_BFS_label_dictionary()

        #switch_map = self.get_connectivity_matrix(node_dic)

        toolbox = base.Toolbox()
        creator.create("FitnessMin", base.Fitness, weights=(-1.0,))
        creator.create("Individual", list, fitness=creator.FitnessMin)
        toolbox.register("indices", random.sample, avilable_rows, num_nodes)
        toolbox.register("individual", tools.initIterate, creator.Individual,
                         toolbox.indices)
        toolbox.register("population", tools.initRepeat, list,
                         toolbox.individual)

        toolbox.register("mate", tools.cxOrdered)
        toolbox.register("mutate", tools.mutShuffleIndexes, indpb=0.05)



        def evaluation(individual):
            cost = 0

            for node_idx, node_assignee in enumerate(individual):
                if node_idx >= self.get_number_of_nodes(True):
                    break
                current_node = nodes[node_idx]
                for neighb in self._my_graph.neighbors(current_node):
                    neighb_idx = node_dic[neighb]
                    neighb_assignee = individual[neighb_idx]
                    if not routing_template[node_assignee][neighb_assignee]:
                        cost += 1

            return cost,

        toolbox.register("evaluate", evaluation)
        toolbox.register("select", tools.selTournament, tournsize = 50)

        fit_stats = tools.Statistics(key=operator.attrgetter("fitness.values"))
        fit_stats.register('mean', np.mean)
        fit_stats.register('min', np.min)

        pop = toolbox.population(n=200)

        bfs_set = set(
            self.get_BFS_label_dictionary().values())
        bfs_set.update(range(num_nodes))
        pop.insert(0, creator.Individual(list(bfs_set))) # adding bfs solution as an initial guess
        pop.insert(10, creator.Individual(list(bfs_set)))  # adding bfs solution as an initial guess
        pop.insert(20, creator.Individual(list(bfs_set)))  # adding bfs solution as an initial guess
        pop.insert(30, creator.Individual(list(bfs_set)))  # adding bfs solution as an initial guess
        pop.insert(40, creator.Individual(list(bfs_set)))  # adding bfs solution as an initial guess
        pop.insert(50, creator.Individual(list(bfs_set)))  # adding bfs solution as an initial guess
        pop.insert(60, creator.Individual(list(bfs_set))) # adding bfs solution as an initial guess
        pop.insert(70, creator.Individual(list(bfs_set)))  # adding bfs solution as an initial guess
        pop.insert(80, creator.Individual(list(bfs_set)))  # adding bfs solution as an initial guess
        pop.insert(90, creator.Individual(list(bfs_set)))  # adding bfs solution as an initial guess
        pop.insert(100, creator.Individual(list(bfs_set)))  # adding bfs solution as an initial guess
        pop.insert(110, creator.Individual(list(bfs_set)))  # adding bfs solution as an initial guess

        result, log = algorithms.eaSimple(pop, toolbox,
                                          cxpb=0.5, mutpb=0.3,
                                          ngen=500, verbose=False,
                                          stats=fit_stats)

        best_individual = tools.selBest(result, k=1)[0]
        print('Fitness of the best individual: ', evaluation(best_individual)[0])

        plt.figure(figsize=(11, 4))
        plots = plt.plot(log.select('min'), 'c-', log.select('mean'), 'b-')
        plt.legend(plots, ('Minimum fitness', 'Mean fitness'), frameon=True)
        plt.ylabel('Fitness')
        plt.xlabel('Iterations')
        plt.show()

        return dict(zip(nodes, best_individual))




    def _make_homogenous_node(self, curr_node, connectivity_dic, start_type):

        new_nodes = []

        for neighb, on_edge_char_set in connectivity_dic.iteritems():
            if curr_node != neighb:
                new_node = S_T_E(start_type=start_type, is_report=curr_node.report, is_marked=True,
                                 id=self.get_new_id(),
                                 symbol_set=on_edge_char_set,
                                 adjacent_S_T_E_s=None,
                                 report_residual= curr_node.report_residual,
                                 report_code=curr_node.report_code)

                self.add_element(new_node, connect_to_fake_root= False) # it will not be coonected to fake_root since the graph is not homogeneous at the moment
                new_nodes.append(new_node)
                self.add_edge(neighb, new_node, label = new_node.symbols, start_type = new_node.start_type)
                out_edges = self._my_graph.out_edges(curr_node, data = True, keys = False)

                for edge in out_edges:
                    if edge[1] != edge[0]:
                        self.add_edge(new_node, edge[1], label = edge[2]['label'], start_type = edge[2]['start_type'])
                    else:
                        continue # not necessary for self loops
            else:
                assert start_type == StartType.non_start, "self loops should be in non start category"
                continue # self-loops node will be processed later

        return new_nodes


    def does_have_self_loop(self):
        """
        check if there is a node in the graph that have self loop
        :return: True if there is a node otherwise return False
        """
        for node in self._my_graph.nodes:
            if self.does_STE_has_self_loop(node):
                #TODO add log
                return True

        return False

    #TODO rename to node instead of ste
    def does_STE_has_self_loop(self, node):
        return node in self._my_graph.neighbors(node)

    def print_summary(self, print_detailed_final_states = False, logo = ""):
        print"******************** Summary {}********************".format(logo)
        print "report for", self._id
        print "Number of nodes = ", self.nodes_count
        print "Number of edges = ", self.get_number_of_edges()
        print "Number of start nodes = ", self.number_of_start_nodes
        print "Number of report nodes = ", self.number_of_report_nodes
        print "does have all_input = ", self.does_have_all_input()
        print "does have special element = ", self.does_have_special_elements()
        print "is Homogenous = ", self.is_homogeneous
        print "stride value = ", self.stride_value
        print "average number of intervals per STE = ", self.get_average_intervals()
        if print_detailed_final_states:
            self._print_final_states_detail()

        print "#######################################################"

    def combine_finals_with_same_symbol_set(self, same_residuals_only, same_report_code):
        assert self.is_homogeneous, "This operation works only for homogeneous"
        equal_nodes = {}
        final_nodes = self.get_filtered_nodes(lambda node: node.report)
        for f_node in final_nodes:
            set_found = False
            f_node_neighbors = set(self._my_graph.neighbors(f_node)) - set([f_node])
            for equal_key in equal_nodes:
                if (not same_residuals_only or (f_node.report_residual == equal_key.report_residual))and\
                        f_node.symbols.is_symbolset_a_subset(equal_key.symbols) and \
                        equal_key.symbols.is_symbolset_a_subset(f_node.symbols) and \
                        self.does_STE_has_self_loop(equal_key) == self.does_STE_has_self_loop(f_node) and \
                        f_node_neighbors == (set(self._my_graph.neighbors(equal_key)) - set([equal_key]) )and \
                        (not same_report_code or (f_node.report_code == equal_key.report_code)):
                    set_found = True
                    equal_nodes[equal_key].add(f_node)
                    break

            if not set_found:
                equal_nodes[f_node] = set([f_node])

        for equal_set in equal_nodes.values():
            if len(equal_set) > 1: # nodes can be merged
                equal_list = list(equal_set)
                for to_merge_node in equal_list[1:]:
                    for pred in self._my_graph.predecessors(to_merge_node):
                        if pred == to_merge_node:
                            continue
                        self.add_edge(pred,equal_list[0])
                    self.delete_node(to_merge_node)


    #TODO incomplete implementation
    def minimize_hopcraft(self):
        assert not self.is_homogeneous(), "automata should be in non homogeneous state"
        partitions_list = []
        k = 3
        q = deque()
        pass

    def _print_final_states_detail(self):
        final_states_with_self_loop = 0
        final_states_with_back_connection = 0
        symbol_set_dict = {}

        final_nodes = self.get_filtered_nodes(lambda ste: ste.report)

        for idx_fnode,f_node in enumerate(final_nodes):
            if self.does_STE_has_self_loop(f_node):
                final_states_with_self_loop+=1

            for neighb in self._my_graph.neighbors(f_node):
                if not neighb.report:
                    final_states_with_back_connection += 1
                    break
            found_symbol_set_key = False
            for key in symbol_set_dict:
                if f_node.is_symbolset_a_subsetof_self_symbolset(key.get_symbols()) and \
                        key.is_symbolset_a_subsetof_self_symbolset(f_node.get_symbols()):
                    found_symbol_set_key = True
                    symbol_set_dict[key] += 1
                    break
            if not found_symbol_set_key:
                symbol_set_dict[f_node] = 1

        print "number of final nodes with self connection:", final_states_with_self_loop
        print "number of final nodes with back connection:", final_states_with_back_connection
        print "number of different symbol sets", len(symbol_set_dict)

    def split(self):
        """
        split the current automata and rturn both of them
        :return:
        """

        assert self.is_homogeneous, "This operation is available only for homogeneous"
        assert not self.does_have_special_elements()

        left_automata = Automatanetwork(id = self._id+"_split1",is_homogenous= True, stride= int(self.stride_value/2))
        right_automata = Automatanetwork(id = self._id+"_split2", is_homogenous=True, stride=int(self.stride_value/2))
        self.unmark_all_nodes()
        self.fake_root.marked = True  # fake root has been added in the constructor for both splited graphs

        self._split_node(self.fake_root, left_automata = left_automata, right_automata= right_automata,
                         id_dic={FakeRoot.fake_root_id:FakeRoot.fake_root_id})

        left_automata.last_assigned_id = self.last_assigned_id
        right_automata.last_assigned_id = self.last_assigned_id
        return left_automata, right_automata

    def _split_node(self, node, left_automata, right_automata, id_dic):
        """

        :param node: the node taht is going to be splitted
        :param left_automata: the first automata to put the first split
        :param right_automata: the second automata to put the second split
        :return:
        """


        for neighb in self._my_graph.neighbors(node):
            if not neighb.marked:
                neighb.marked = True
                left_symbols, right_symbols = neighb.split_symbols()
                #new_left_id, new_right_id = left_automata.get_new_id(), right_automata.get_new_id()
                #assert new_left_id == new_right_id, "ID's should stay similar"
                id_dic[neighb.id] = neighb.id

                left_ste = S_T_E(start_type=neighb.start_type, is_report = neighb.report,
                                 is_marked = True, id=neighb.id, symbol_set= left_symbols, adjacent_S_T_E_s=None,
                                 report_residual=neighb.report_residual, report_code=neighb.report_code)
                left_automata.add_element(left_ste)

                right_ste = S_T_E(start_type=neighb.start_type, is_report = neighb.report,
                                 is_marked=True, id=neighb.id, symbol_set=right_symbols, adjacent_S_T_E_s=None,
                                  report_residual=neighb.report_residual, report_code=neighb.report_code)
                right_automata.add_element(right_ste)

                self._split_node(neighb, left_automata=left_automata, right_automata=right_automata, id_dic=id_dic)

            left_ste_src = left_automata.get_STE_by_id(id_dic[node.id])
            left_ste_dst = left_automata.get_STE_by_id(id_dic[neighb.id])
            if not left_ste_src.start_type == StartType.fake_root:
                left_automata.add_edge(left_ste_src, left_ste_dst)

            right_ste_src = right_automata.get_STE_by_id(id_dic[node.id])
            right_ste_dst = right_automata.get_STE_by_id(id_dic[neighb.id])
            if not right_ste_src.start_type == StartType.fake_root:
                right_automata.add_edge(right_ste_src, right_ste_dst)

    def _find_next_states(self, current_active_states, input):
        """

        :param current_active_states: a set of current active states
        :param input: an iterable symbol set
        :return: (True/False) if there is a report element in new states, (Set) new states
        """

        assert len(input) == self.stride_value
        new_active_states = set()
        is_report = False
        report_residual_details = [False] * self.stride_value

        for act_st in current_active_states:
            if self.is_homogeneous:
                for neighb in self._my_graph.neighbors(act_st):
                    can_accept  = neighb.symbols.can_accept(input_pt=PackedInput(input))
                    temp_report = can_accept and neighb.report
                    is_report = is_report or temp_report
                    if can_accept:
                        new_active_states.add(neighb)
                        if temp_report:
                            report_residual_details[(neighb.report_residual-1)% self.stride_value] = True
            else:
                out_edges = self._my_graph.out_edges(act_st, data=True, keys=False)
                for edge in out_edges:
                    can_accept= edge[2]['label'].can_accept(input_pt=PackedInput(input))
                    temp_report = can_accept and edge[1].report
                    is_report = is_report or temp_report
                    if can_accept:
                        new_active_states.add(edge[1])
                        if temp_report:
                            report_residual_details[(edge[1].report_residual-1) %self.stride_value] = True

        return is_report, new_active_states, report_residual_details

    def feed_input(self, input_stream, offset, jump):


        assert offset<jump, "this condition should be met"

        mask = [1 if offset <= i < (offset + self.stride_value) else 0 for i in range(jump)]

        active_states = {self.fake_root}

        if self.is_homogeneous:
            all_start_states = [all_start_neighb for all_start_neighb in self._my_graph.neighbors(self.fake_root)
                                if all_start_neighb.start_type == StartType.all_input]
        else:
            all_start_edges = [all_start_edge for all_start_edge in
                               self._my_graph.out_edges(self.fake_root, data=True, keys=False)
                               if all_start_edge[2]['start_type'] == StartType.all_input]

        for input in input_stream:
            input=tuple(itertools.compress(input, mask))
            is_report, new_active_states, report_residual_details =\
                self._find_next_states(current_active_states=active_states, input=input)

            if self.is_homogeneous:
                for all_start_state in all_start_states:
                    can_accept= all_start_state.symbols.can_accept(input=input)
                    temp_report = can_accept and all_start_state.report
                    is_report = is_report or temp_report
                    if can_accept:
                        new_active_states.add(all_start_state)
                        if temp_report:
                            report_residual_details[(all_start_state.report_residual-1) % self.stride_value] = True
            else:
                for all_start_edge in all_start_edges:
                    can_accept = all_start_edge[2]['label'].can_accept(input=input)
                    temp_report = can_accept and all_start_edge[1].report
                    is_report = is_report or temp_report
                    if can_accept:
                        new_active_states.add(all_start_edge[1])
                        if temp_report:
                            report_residual_details[(all_start_edge.report_residual-1) % self.stride_value] = True

            active_states = new_active_states
            #TODO isn't it better to return report codes?
            yield active_states, is_report, report_residual_details

    def count_interconnect_activity(self, input_stream, inbound_set_list, outbound_set_list):

        """
        This function receives an input file and return the acrtivity count. each item in inbound_set_list and outbound_set_list
        is a set.
        for inbound_set_list, if any of the predeccors of items in each set is active, I will increment the appropriate counter for that set in the
        output list.
        For outbound_set_list, if and of the item in a set is active, I will increment the corresponding counter.
        :param input_file_path: path of the input file
        :param inbound_set_list: a list of sets of STEs
        :param outbound_set_list: a list of sets of STEs
        :return: two lists of ints. First for inbound STEs and the second one for outbound items
        """

        inb_counter_list = [0 for _ in range(len(inbound_set_list))]
        out_counter_list = [0 for _ in range(len(outbound_set_list))]

        input_gen = self.feed_input(input_stream=input_stream, offset=0, jump=self.stride_value)

        for in_s_idx, in_s in enumerate(inbound_set_list):
            for node in in_s:
                if node.start_type==StartType.start_of_data:
                    inb_counter_list[in_s_idx] = 1

        for active_states, _, _ in input_gen:
            for inbound_set_idx, inbound_set in enumerate(inbound_set_list):
                for current_ste in inbound_set:
                    if current_ste.sart_type == StartType.all_input:
                        inb_counter_list[inbound_set_idx] += 1
                        break

                    preds = set(self._my_graph.predecessors(current_ste))
                    if preds.intersection(active_states):
                        inb_counter_list[inbound_set_idx] += 1
                        break

            for outbound_set_idx, outbound_set in enumerate(outbound_set_list):
                if outbound_set.intersection(active_states):
                    out_counter_list[outbound_set_idx] += 1

        return inb_counter_list, out_counter_list

    def emulate_AP(self, input_stream):
        """
        This function emulate the real two stage automata
        :param input_file: file to be feed to the input
        :return:
        """
        assert not self.does_have_all_input(), "this method does not work on automatas with all_start input"
        assert self.is_homogeneous

        active_states = {self.fake_root}  # active states, only fake root initially
        report_residual_details = [False] * self.stride_value

        for input_symbol in itertools.izip(*[iter(input_stream)]*self.stride_value):

            potential_next_states = set()
            for aste in active_states:
                potential_next_states.update(self._my_graph.neighbors(aste))

            active_states = set() # search for new active states among potential next states
            is_report = False #

            for pns in potential_next_states:

                can_accept = pns.symbol.can_accept(PackedInput(alphabet_point=input_symbol))
                temp_report = can_accept and pns.report
                is_report = is_report or temp_report
                if can_accept:
                    active_states.add(pns)

                if temp_report:
                    report_residual_details[pns.report_residual] = True

            yield active_states, is_report, report_residual_details


    def remove_ors(self):
        assert self.is_homogeneous, "automata should be homogeneous"
        to_be_deleted_ors= []
        for node in self._my_graph.nodes:
            if node == self.fake_root:
                continue
            if node.type == ElementsType.OR:
                #TODO remove s at the end
                for pre_childs in self._my_graph.predecessors(node):
                    if pre_childs == node:
                        continue

                    if node.report:
                        pre_childs.report = True
                        pre_childs.report_code = node.report_code
                        pre_childs.report_residual = node.report_residual

                    for post_childs in self._my_graph.neighbors(node):
                        if post_childs == node:
                            continue

                        self.add_edge(pre_childs, post_childs)

                to_be_deleted_ors.append(node)

        for or_node in to_be_deleted_ors:
            self.delete_node(or_node)

    def does_have_all_input(self):
        """
        check if there is a node that has an all input property
        :return: True if there is.
        """
        for node in self._my_graph.neighbors(self.fake_root):
            if node.start_type == StartType.all_input:
                return True
        return False

    def remove_all_start_nodes(self):
        """
        this funstion add a new node that accepts Dot Kleene start and connect it to all "all_input nodes"
        please note that we assume all start nodes are not report nodes
        :return: a graph taht does not have any start node with all_input condition
        """

        assert self.is_homogeneous and self.stride_value == 1,\
            "Graph should be in homogenous state to handle this situation and alaso it should be single stride"

        if not self.does_have_all_input():
            return

        star_node = S_T_E(start_type = StartType.start_of_data, is_report=False, is_marked=False,
                          id=self.get_new_id(), symbol_set=PackedIntervalSet.get_star(dim=1), adjacent_S_T_E_s=None,
                          report_residual=-1, report_code=-1)

        self.add_element(to_add_element = star_node, connect_to_fake_root = True)

        self.add_edge(star_node, star_node)

        for node in self._my_graph.neighbors(self.fake_root):

            if node == star_node:
                continue
            if node.start_type == StartType.all_input:
                node.start_type=StartType.start_of_data
                self.add_edge(star_node,node)


    def get_connected_components_size(self):
        undirected_graph= self._my_graph.to_undirected()
        undirected_graph.remove_node("fake_root")
        return tuple(len(g) for g in sorted(nx.connected_components(undirected_graph), key=len, reverse=True))

    def get_connected_components_as_automatas(self):
        assert not self.does_have_special_elements(), "This function does not support automatas with special elements"
        assert self.is_homogeneous, "Graph should be in homogeneous state"
        undirected_graph = self._my_graph.to_undirected()
        undirected_graph.remove_node(self.fake_root)
        ccs =  nx.connected_components(undirected_graph)
        splitted_automatas = []

        for cc_idx, cc in enumerate(ccs):
            sg = self._my_graph.subgraph(cc)
            new_graph = nx.MultiDiGraph(sg)
            new_autoama = Automatanetwork._from_graph(id=self._id + str(cc_idx),is_homogenous=True, graph = new_graph,
                                                      stride=self.stride_value, last_assigned_id=self.last_assigned_id)
            splitted_automatas.append(new_autoama)

        return splitted_automatas

    def does_have_special_elements(self):
        for nodes in self._my_graph.nodes():
            if nodes.is_special_element():
                return True
        return False

    def left_merge(self, merge_reports=False, same_residuals_only=False, same_report_code=False):
        assert self.is_homogeneous, "This function is working only for homogeneous case!"
        self.unmark_all_nodes()
        dq = deque()

        self.fake_root.marked = True
        dq.appendleft(self.fake_root)

        while dq:

            current_node = dq.pop()

            for children in list(self._my_graph.neighbors(current_node)):
                if children.marked:
                    continue

                if children not in self.nodes: # this children has been deleted
                    continue

                if children == current_node:
                    continue  # self loop
                for second_children in list(self._my_graph.neighbors(current_node)):
                    if second_children not in self.nodes:
                        continue  # deleted node
                    if second_children == children :
                        continue  # comparing the same node
                    if second_children.marked:
                        continue

                    if self._can_left_merge_stes(children, second_children, merge_reports,
                                                 same_residuals_only, same_report_code):
                        first_children_neighb = set(self._my_graph.neighbors(children))
                        for second_children_neigh in self._my_graph.neighbors(second_children):
                            if second_children_neigh in first_children_neighb:
                                continue
                            self.add_edge(children, second_children_neigh)

                        self.delete_node(second_children)

            for children in self._my_graph.neighbors(current_node):
                if not children.marked:
                    children.marked = True
                    dq.appendleft(children)

    def right_merge(self, merge_reports=False, same_residuals_only=False, same_report_code=False):

        assert self.is_homogeneous, "This function is working only for homogeneous case!"
        self.unmark_all_nodes()
        dq = deque()

        report_nodes = self.get_filtered_nodes(lambda n: n.report)
        for report_node in report_nodes:
            report_node.marked = True
            dq.appendleft(report_node)

        while dq:

            current_node = dq.pop()

            for parent in list(self._my_graph.predecessors(current_node)):

                if parent.marked:
                    continue

                if parent not in self.nodes: # this parent has been deleted
                    continue

                if parent == current_node:
                    continue # self loop

                for second_parent in list(self._my_graph.predecessors(current_node)):
                    if second_parent not in self.nodes:
                        continue  # deleted node
                    if second_parent == parent :
                        continue  # comparing the same node
                    if second_parent.marked:
                        continue

                    if self._can_right_merge_stes(parent, second_parent, merge_reports , same_residuals_only , same_report_code ):
                        first_children_parents = set(self._my_graph.predecessors(parent))
                        for second_children_neigh in self._my_graph.predecessors(second_parent):
                            if second_children_neigh in first_children_parents:
                                continue
                            self.add_edge(second_children_neigh, parent)

                        self.delete_node(second_parent)

            for parent in self._my_graph.predecessors(current_node):
                if not parent.marked:
                    parent.marked = True
                    dq.appendleft(parent)

    def combine_symbol_sets(self):
        assert self.is_homogeneous, "Automata should be in homogeneous"
        """
        this function combines the symbol sets of two stes with a same parent and a same child
        :return:
        """
        self.unmark_all_nodes()

        dq = deque()
        self.fake_root.marked = True
        dq.appendleft(self.fake_root)

        while dq:
            current_node = dq.pop()

            for first_neighb_node in list(self._my_graph.neighbors(current_node)):
                if first_neighb_node not in self.nodes:
                    continue  # deleted node
                for sec_neighb_node in list(self._my_graph.neighbors(current_node)):
                    if sec_neighb_node not in self.nodes:
                        continue  # deleted node
                    if first_neighb_node == sec_neighb_node:
                        continue
                    if self._can_combine_symbol_set(fst_ste=first_neighb_node, sec_ste= sec_neighb_node):
                        for interval in sec_neighb_node.symbols:
                            first_neighb_node.symbols.add_interval(interval)
                        self.delete_node(sec_neighb_node)

            for node in self._my_graph.neighbors(current_node):
                if not node.marked:
                    node.marked = True
                    dq.appendleft(node)

    def _can_combine_symbol_set(self, fst_ste, sec_ste):
        if fst_ste.start_type != sec_ste.start_type:
            return False

        if fst_ste.report != sec_ste.report:
            return False

        if self.does_STE_has_self_loop(fst_ste) != self.does_STE_has_self_loop(sec_ste):
            return False

        fst_ste_neighbors = set(self._my_graph.neighbors(fst_ste))

        if fst_ste in fst_ste_neighbors:
            fst_ste_neighbors.remove(fst_ste)

        if len(fst_ste_neighbors) != 1:
            return False

        sec_ste_neighbors = set(self._my_graph.neighbors(sec_ste))

        if sec_ste in sec_ste_neighbors:
            sec_ste_neighbors.remove(sec_ste)

        if len(sec_ste_neighbors) != 1:
            return False

        if sec_ste_neighbors != fst_ste_neighbors:
            return False

        fst_ste_predecessors = set(self._my_graph.predecessors(fst_ste))

        if fst_ste in fst_ste_predecessors:
            fst_ste_predecessors.remove(fst_ste)

        if len(fst_ste_predecessors) != 1:
            return False

        sec_ste_predecessors = set(self._my_graph.predecessors(sec_ste))

        if sec_ste in sec_ste_predecessors:
            sec_ste_predecessors.remove(sec_ste)

        if len(sec_ste_predecessors) != 1:
            return False

        if sec_ste_predecessors != fst_ste_predecessors:
            return False

        return True

    def _can_left_merge_stes(self, fst_ste, sec_ste, merge_reports=False,
                             same_residuals_only=False, same_report_code=False):

        if fst_ste.start_type != sec_ste.start_type:
            return False

        if fst_ste.report != sec_ste.report:
            return False

        if not fst_ste.symbols.is_symbolset_a_subset(sec_ste.symbols) or not \
                sec_ste.symbols.is_symbolset_a_subset(fst_ste.symbols):
            return False

        if self.does_STE_has_self_loop(fst_ste) != self.does_STE_has_self_loop(sec_ste):
            return False

        if fst_ste.report:  # we have checked other is also the same previously
            if not merge_reports:
                return False

            if same_residuals_only:
                if fst_ste.report_residual != sec_ste.report_residual:
                    return False

            if same_report_code:
                if fst_ste.report_code != sec_ste.report_code:
                    return False

        fst_ste_parents = set(self._my_graph.predecessors(fst_ste)) - set([fst_ste])
        sec_ste_parents = set(self._my_graph.predecessors(sec_ste)) - set([sec_ste])

        return fst_ste_parents == sec_ste_parents

    def _can_right_merge_stes(self,fst_ste, sec_ste, merge_reports = False, same_residuals_only = False, same_report_code = False):

        if fst_ste.start_type != sec_ste.start_type:
            return  False

        if fst_ste.report != sec_ste.report:
            return  False

        if not fst_ste.symbols.is_symbolset_a_subset(sec_ste.symbols) or not \
                sec_ste.symbols.is_symbolset_a_subset(fst_ste.symbols):
            return False

        if self.does_STE_has_self_loop(fst_ste) != self.does_STE_has_self_loop(sec_ste):
            return  False

        if fst_ste.report: # we have checked other is also the same previously
            if not merge_reports:
                return False

            if same_residuals_only:
                if fst_ste.report_residual!=sec_ste.report_residual:
                    return False

            if same_report_code:
                if fst_ste.report_code!=sec_ste.report_code:
                    return False

        fst_ste_children = set(self._my_graph.neighbors(fst_ste)) - {fst_ste}
        sec_ste_children = set(self._my_graph.neighbors(sec_ste)) - {sec_ste}

        return fst_ste_children == sec_ste_children

    def get_STEs_out_degree(self):
        out_degree_list = []
        for node in self.nodes:
            if node.start_type == StartType.fake_root:
                continue

            out_degree_list.append(self._my_graph.out_degree(node))

        return tuple(out_degree_list)

    def get_STEs_in_degree(self):
        in_degree_list = []
        for node in self.nodes:
            if node.get_start() == StartType.fake_root:
                continue

            in_degree_list.append(self._my_graph.in_degree(node))

        return tuple(in_degree_list)

    def max_STE_in_degree(self):
        """
        return the maximum fan in ampng all the STEs
        :return:
        """
        return max(self.get_STEs_in_degree())

    def max_STE_out_degree(self):
        """
        return the maximum fan out ampng all the STEs
        :return:
        """
        return max(self.get_STEs_out_degree())

    def set_max_fan_in(self, max_fan_in):
        assert self.is_homogeneous, "This function works only for homogeneous automatas"
        assert max_fan_in > 2

        self.unmark_all_nodes()

        dq = deque()
        self.fake_root.marked = True
        dq.appendleft(self.fake_root)

        while dq:

            current_node = dq.pop()

            for neighb in self._my_graph.neighbors(current_node):
                if not neighb.marked:
                    neighb.marked = True
                    dq.appendleft(neighb)

            if current_node.start_type == StartType.fake_root: # fake root does not have fan in constrain
                continue

            is_start = current_node.start_type == StartType.start_of_data or \
                       current_node.start_type == StartType.all_input
            curr_node_in_degree = self._my_graph.in_degree(current_node) - is_start
            if curr_node_in_degree > max_fan_in:
                is_self_loop = self.does_STE_has_self_loop(current_node)

                number_of_new_copies = int(math.ceil((curr_node_in_degree - is_self_loop)/(max_fan_in - is_self_loop)))
                predecessors = list(self._my_graph.predecessors(current_node))
                if is_self_loop:
                    predecessors.remove(current_node)

                if is_start:
                    predecessors.remove(self._fake_root)

                step_size = max_fan_in - is_self_loop

                _recently_added_nods = []

                for i in range(number_of_new_copies):

                    new_STE = S_T_E(start_type=current_node.start_type, is_report=current_node.report,
                                    is_marked=True, id=self.get_new_id(), symbol_set=current_node.symbols.clone(),
                                    adjacent_S_T_E_s=None, report_residual=current_node.report_residual,
                                    report_code=current_node.report_code)

                    _recently_added_nods.append(new_STE)

                    self.add_element(new_STE)

                    for neighb in self._my_graph.neighbors(current_node):
                        self.add_edge(new_STE, new_STE if neighb == current_node else neighb)

                    for pred in predecessors[i*step_size:min(len(predecessors), (i+1)*step_size)]:
                        self.add_edge(pred, new_STE)

                for neighb in self._my_graph.neighbors(current_node):
                    if neighb != current_node and not neighb in dq:
                        dq.appendleft(neighb)
                self.delete_node(current_node)

    def set_max_fan_out(self, max_fan_out):
        assert self.is_homogeneous, "This function works only for homogeneous automatas"
        assert max_fan_out > 2

        self.unmark_all_nodes()

        dq = deque()
        report_nodes = self.get_filtered_nodes(lambda n: n.report)

        for report_node in report_nodes:
            report_node.marked = True
            dq.appendleft(report_node)

        while dq:
            current_node = dq.pop()
            for pred in self._my_graph.predecessors(current_node):
                if not pred.marked:
                    pred.marked = True
                    dq.appendleft(pred)

            if current_node.start_type == StartType.fake_root: # fake root does not have fan out constraint
                continue

            curr_node_out_degree = self._my_graph.out_degree(current_node)
            if curr_node_out_degree > max_fan_out:
                is_self_loop = self.does_STE_has_self_loop(current_node)

                number_of_new_copies = int(math.ceil((curr_node_out_degree - is_self_loop)/(max_fan_out - is_self_loop)))
                neighbors = list(self._my_graph.neighbors(current_node))
                if is_self_loop:
                    neighbors.remove(current_node)

                step_size = max_fan_out - is_self_loop
                for i in range(number_of_new_copies):

                    new_STE = S_T_E(start_type=current_node.start_type, is_report=current_node.report,
                                    is_marked=True, id=self.get_new_id(), symbol_set=current_node.symbols.clone(),
                                    adjacent_S_T_E_s=None, report_residual=current_node.report_residual,
                                    report_code=current_node.report_code)

                    self.add_element(new_STE)

                    for pred in self._my_graph.predecessors(current_node):
                        self.add_edge(new_STE if pred == current_node else pred, new_STE)

                    for neighb in neighbors[i*step_size:min(len(neighbors), (i+1)*step_size)]:
                        self.add_edge(new_STE, neighb)

                for pred in self._my_graph.predecessors(current_node):
                    if pred != current_node and not pred in dq:
                        dq.appendleft(pred)
                self.delete_node(current_node)

    def does_all_nodes_marked(self):
        for node in self._my_graph.nodes():
            if not node.marked:
                return False
        return True


def compare_strided(only_report, file_path,*automatas ):
    # with open(file_path, 'rb') as f:
    #     file_content = f.read()
    # #TODO does not work for big files
    # byte_file_content = bytearray(file_content)

    strides = [sum(stride for stride in map(lambda x:x.stride_value, automata)) for automata in automatas]
    max_stride = max(strides)
    gens =[]

    for idx, automata in enumerate(automatas):
        sum_stride_value = 0
        strided_gen =[]
        for strided_automata in automata:
            strided_gen.append(strided_automata.feed_input(
                utility.multi_byte_stream(file_path=file_path,
                                          chunk_size=strides[idx]),
                offset=sum_stride_value,
                jump=strides[idx]))
            sum_stride_value += strided_automata.stride_value
        gens.append(strided_gen)



    file_size = os.path.getsize(file_path)

    for _ in tqdm(itertools.count(), total=math.ceil(file_size / max_stride), unit='symbol'):

        first_automata_ste_set = None
        first_automata_report = False
        for idx, generator_set in enumerate(gens):

            try:
                for _ in range(int(max_stride/strides[idx])):

                    temp_result_set_list=[]
                    for gen in generator_set:
                        result_set, _, _ = next(gen)
                        temp_result_set_list.append(result_set)

                    intersection_set = set(temp_result_set_list[0])
                    for result_set in temp_result_set_list[1:]:
                        intersection_set = intersection_set.intersection(result_set)

                    for result_set in temp_result_set_list:
                        result_set.clear()
                        result_set.update(intersection_set)

                temp_is_report = False
                for ste in intersection_set:
                    if ste.report:
                        temp_is_report = True
                        break

                if idx == 0:
                    first_automata_ste_set = intersection_set
                    first_automata_report = temp_is_report
                else:

                    assert temp_is_report == first_automata_report
                    if not only_report:
                        assert first_automata_ste_set == intersection_set


            except StopIteration:
                print "they are equal"
                return


def compare_real_approximate(file_path, automata):
    stride_value = automata.get_stride_value()
    false_reports_exact, false_actives, false_reports_each_cycle, true_total_reports = 0, 0, 0, 0
    false_stat_per_state={}
    real_atm_gen, apprx_atm_gen = automata.feed_file(file_path), automata.emulate_AP(file_path)

    def print_results():
        print "false activated states = \t", false_actives  # number of active states that has been activated wrongly
        print "false reports states = \t", false_reports_exact # false reports states
        print "false reports cycles = \t", false_reports_each_cycle # false reports cycles at the end of max stride
        print "total true reports = \t", true_total_reports #

    itr = 0
    try:
        while True:
            real_active_states, real_is_report, real_report_residual_details = next(real_atm_gen)
            appx_active_states, appx_is_report, appx_report_residual_details = next(apprx_atm_gen)

            real_minus_app = real_active_states - appx_active_states
            #assert len(real_minus_app) == 0, "this brings false positive under question"

            app_minus_real = appx_active_states - real_active_states

            false_actives += len(app_minus_real)
            false_reports_exact += sum([1 if app_ste.report else 0 for app_ste in app_minus_real])
            false_reports_each_cycle += 1 if real_is_report != appx_is_report else 0
            true_total_reports += sum([1 if real_ste.report else 0 for real_ste in real_active_states])

            for app_ste in app_minus_real:
                false_stat_per_state[app_ste] = false_stat_per_state.get(app_ste, 0) + 1


            itr+=1
            if itr % 100000 == 0:
                print_results()
                break


    except StopIteration:
        pass

    print_results()
    return false_actives, false_reports_exact, false_reports_each_cycle, true_total_reports


def compare_input(only_report, check_residuals, file_path, *automatas):
    gens = []
    result = [() for i in range(len(automatas))]
    max_stride = max([sv.stride_value for sv in automatas])

    for a in automatas:
        assert max_stride % a.stride_value == 0
        g = a.feed_input(utility.multi_byte_stream(file_path, a.stride_value), offset=0, jump=a.stride_value)
        gens.append(g)

    try:
        file_size = os.path.getsize(file_path)

        for _ in tqdm(itertools.count(), total=math.ceil(file_size/max_stride), unit='symbol'):
            for idx_g, (g, automata) in enumerate(zip(gens, automatas)):

                total_report_residual_details = []
                is_report = False
                for _ in range(int(max_stride / automata.stride_value)):
                    temp_active_states, temp_is_report, report_residual_details = next(g)
                    total_report_residual_details.extend(report_residual_details)
                    is_report = is_report or temp_is_report

                result[idx_g] =(temp_active_states, is_report, total_report_residual_details)

            for active_state, report_state, total_report_residual_details in result[1:]:
                assert report_state==result[0][1] # check report states
                if check_residuals:
                    assert total_report_residual_details == result[0][2]
                if not only_report:
                    assert active_state == result[0][0] # check current states

    except StopIteration:
        print "They are equal"









