import pycparser # the C parser written in Python
import sys # so we can access command-line args
import pprint # so we can pretty-print our output

import mksymtab

from compiler_utilities import TagStack

import itertools

label_generator = itertools.count()

class Label(object):
    def __init__(self,**kwargs):
        self.kwargs = kwargs
    pass

class CodeBuilder(pycparser.c_ast.NodeVisitor):
    def __init__(self,function_name,symbol_table):
        self.the_code = []
        self.the_symbol_table = symbol_table
        self.the_function_name = function_name
        self.expression_stack = []
        self.state = TagStack()
    def add(self,operation,destination,source1,source2,label=None):
        self.the_code.append((label,operation,destination,source1,source2))
    def genLabel(self,label_type,scope):
        # do stuff here with symbol table
        the_label = "L"+str(label_generator.next())
        self.the_symbol_table.values[the_label] = label_type
        return the_label
    def start_visit(self,node):
        self.the_symbol_table.values.path.append(self.the_function_name)
        self.visit(node)
        del self.the_symbol_table.values.path[-1]
        assert(0 == len(self.the_symbol_table.values.path))
    def visit_Compound(self,node):
        self.generic_visit(node)
        self.expression_stack.append("")
    def visit_Assignment(self,node):
        children = dict(node.children())
        lvalue, rvalue = children["lvalue"], children["rvalue"]
        with self.state.push("lvalue"):
            self.visit(lvalue)
        self.visit(rvalue)
        rvalue = self.expression_stack.pop()
        lvalue = self.expression_stack.pop()
        self.add("=",lvalue,rvalue,"")
        self.expression_stack.append(lvalue)
    def visit_ID(self,node):
        self.expression_stack.append(node.name)
    def visit_Constant(self,node):
        self.expression_stack.append(node.value)
    def visit_Return(self,node):
        self.generic_visit(node)
        self.add("return",self.expression_stack.pop(),"","")
    def visit_BinaryOp(self,node):
        self.generic_visit(node)
        operand1 = self.expression_stack.pop()
        operand2 = self.expression_stack.pop()
        assert(self.the_symbol_table.typeof(operand1) == self.the_symbol_table.typeof(operand2))
        destination = self.genLabel(self.the_symbol_table.typeof(operand1),"local")
        self.add(node.op,destination,operand1,operand2)
        self.expression_stack.append(destination)
    def visit_UnaryOp(self,node):
        if node.op == "&":
            with self.state.push("lvalue"):
                self.generic_visit(node)
            return
        else:
            with self.state.unpush("lvalue"):
                self.generic_visit(node)
        operand1 = self.expression_stack.pop()
        the_type = self.the_symbol_table.typeof(operand1)
        # if the_type is & or * then handle differently
        if node.op == "*":
            assert(isinstance(the_type,tuple))
            dim, ptr_type = the_type
            the_type = ptr_type
        elif node.op == "&":
            the_type = ('',the_type)
        destination = self.genLabel(the_type,"local")
        if node.op == "p++":
            self.add("+",operand1,operand1,1)
            self.expression_stack.append(operand1)
        else:
            if "lvalue" in self.state and node.op == "*":
                pass
            else:
                self.add(node.op,destination,operand1,"")
        if "lvalue" in self.state:
            if node.op == "*":
                self.expression_stack.append(operand1)
            else:
                self.expression_stack.append(destination)
        else:
            self.expression_stack.append(destination)
    def visit_StructRef(self,node):
        StructRef_type = node.type
        self.visit(dict(node.children())["name"])
        if StructRef_type == "->":
            operand1 = self.expression_stack.pop()
            the_type = self.the_symbol_table.typeof(operand1)
            assert(isinstance(the_type,tuple))
            dim, ptr_type = the_type
            the_type = ptr_type
            destination = self.genLabel(the_type,"local")
            self.add("*",destination,operand1,"")    
            self.expression_stack.append(destination)
        if StructRef_type in [".","->"]:
            the_struct = self.expression_stack.pop()
            self.visit(dict(node.children())["field"])
            the_field = self.expression_stack.pop()
            the_struct_type = self.the_symbol_table.typeof(the_struct)
            offset, the_element_type = dict(self.the_symbol_table.offsets_and_types_of_elements(the_struct_type))[the_field]
            pprint.pprint(offset)
            pprint.pprint(the_element_type)
            destination = self.genLabel(the_element_type,"local")
            if "lvalue" in self.state:
                self.add("+",destination,the_struct,offset)
                self.expression_stack.append(destination)
            else:
                self.add("load",destination,the_struct,offset)
                self.expression_stack.append(destination)
            #assert(False)
        else: assert(False)
    def visit_For(self,node):
        init, cond, next, stmt = node.init, node.cond, node.next, node.stmt
        self.visit(init)
        junk = self.expression_stack.pop()        
        top_of_loop = self.genLabel(Label(),"local")
        bottom_of_loop = self.genLabel(Label(),"local")
        self.add("","","","",label=top_of_loop)
        self.visit(cond)
        conditional = self.expression_stack.pop()
        self.add("conditional_branch",bottom_of_loop,conditional,"")
        self.visit(stmt)
        junk = self.expression_stack.pop()        
        self.visit(next)
        junk = self.expression_stack.pop()
        self.add("unconditional_branch",top_of_loop,"","")
        self.add("","","","",label=bottom_of_loop)
    def visit_While(self,node):
        cond, stmt = node.cond, node.stmt        
        top_of_loop = self.genLabel(Label(),"local")
        bottom_of_loop = self.genLabel(Label(),"local")
        self.add("","","","",label=top_of_loop)
        self.visit(cond)
        conditional = self.expression_stack.pop()
        self.add("conditional_branch",bottom_of_loop,conditional,"")
        self.visit(stmt)
        junk = self.expression_stack.pop()        
        self.add("unconditional_branch",top_of_loop,"","")
        self.add("","","","",label=bottom_of_loop)
    def visit_If(self,node):
        cond, iffalse, iftrue = node.cond, node.iffalse, node.iftrue        
        then_part = self.genLabel(Label(),"local")
        else_part = self.genLabel(Label(),"local")
        end_part = self.genLabel(Label(),"local")
        self.visit(cond)
        conditional = self.expression_stack.pop()
        self.add("conditional_branch",then_part,conditional,"")
        self.add("unconditional_branch",else_part,"","")
        self.add("","","","",label=then_part)        
        self.visit(iftrue)
        junk = self.expression_stack.pop()        
        self.add("unconditional_branch",end_part,"","")
        self.add("","","","",label=else_part)                
        if iffalse is not None:
            self.visit(iffalse)
            junk = self.expression_stack.pop()        
        self.add("","","","",label=end_part)
    
        
        

if __name__ == "__main__":
    if len(sys.argv) > 1:    # optionally support passing in some code as a command-line argument
        code_to_parse = sys.argv[1]
    else: # this can not handle the typedef and struct below correctly. Need to work on it.
        code_to_parse = """
int foo(int a, int b) {
    if (a == b) {
        return 1;
    } else {
        return 0;
    };
};
int bar(int c, int d) {
    if (c == d) {
        return 1;
    };
    return 0;
};
typedef struct linked_list {
    int item;
    struct linked_list * next;
} linked_list;
int * test(linked_list * node) {
    while (node->next) {
        node = (*node).next;
    };
    return &(node->item);
};
int sum_of_squares(int x) {
    int i;
    int result;
    result = 0;
    for (i = 1; i <= x; i++) {
        result = result + i*i;
    };
    return result;
};
"""
    cparser = pycparser.c_parser.CParser()
    parsed_code = cparser.parse(code_to_parse)
    parsed_code.show()
    st = mksymtab.makeSymbolTable(parsed_code)
    #pprint.pprint(st.values.values)
    #pprint.pprint(st.types.values)
    functions = (dict(st.functions()))
    #pprint.pprint(st.values.path)
    for key,value in functions.items():
        print key
        body = value["{}"]
        body.show()
        cb = CodeBuilder(key,st)
        cb.start_visit(body)
        value["{}"] = cb.the_code
    pprint.pprint(st.values.values)
    