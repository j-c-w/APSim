import automata as atma
from automata.automata_network import compare_input, compare_strided
from anml_zoo import anml_path,input_path,AnmalZoo
from tqdm import tqdm
import pickle
from utility import minimize_automata, multi_byte_stream


# automata1 = atma.parse_anml_file(anml_path[AnmalZoo.Snort])
# automata1.remove_ors()
# automata1.print_summary()
# automatas = automata1.get_connected_components_as_automatas()
#
# to_save_automatas = automatas[:10]
#
# pickle.dump(to_save_automatas, open("snort1-10.pkl", "wb"))

automatas = pickle.load(open('snort1-10.pkl','rb'))

atm = automatas[1]
atm.remove_all_start_nodes()
minimize_automata(atm,merge_reports=True, same_residuals_only=True, same_report_code=True)

atm.draw_graph('1.svg', draw_edge_label=False, use_dot = True, write_node_labels = True)

st2= atm.get_single_stride_graph()
st2.draw_graph('2.svg', draw_edge_label=False, use_dot = True, write_node_labels = True)
st4=st2.get_single_stride_graph()
st4.draw_graph('4.svg', draw_edge_label=False, use_dot = True, write_node_labels = True)

st2.make_homogenous()
minimize_automata(st2,merge_reports=True, same_residuals_only=True, same_report_code=True)
st2.print_summary()
st4.make_homogenous()
st4.print_summary()
compare_input(True, True, input_path[AnmalZoo.Snort],*(atm,st2, st4))
#automatas[0].draw_graph('2.svg', draw_edge_label=False, use_dot = True, write_node_labels = True)

exit (0)
st8=st4.get_single_stride_graph()
st8.print_summary()
st16=st8.get_single_stride_graph()
st16.print_summary()
st32=st16.get_single_stride_graph()
st32.print_summary()






