import os
import pytest
from prism_reviewer.codelens.parser import UniversalASTAnalyzer

@pytest.fixture
def analyzer():
    return UniversalASTAnalyzer()

def test_ast_python(analyzer, tmp_path):
    code = """
class MyClass:
    def my_method(self):
        pass

def my_function():
    pass
"""
    file_path = tmp_path / "test.py"
    file_path.write_text(code, encoding="utf-8")
    
    res = analyzer.get_ast_skeleton(str(file_path))
    assert res["mode"] == "ast"
    assert res["file_path"] == str(file_path)
    
    symbols = res["symbols"]
    sym_map = {s["name"]: s["type"] for s in symbols}
    assert "MyClass" in sym_map
    assert sym_map["MyClass"] == "class_definition"
    assert "my_method" in sym_map
    assert sym_map["my_method"] == "function_definition"
    assert "my_function" in sym_map
    assert sym_map["my_function"] == "function_definition"

def test_ast_javascript_typescript(analyzer, tmp_path):
    code = """
class JSClass {
    jsMethod() {}
}
function jsFunc() {}
const arrowFunc = (x) => x * 2;
interface MyInterface {
    prop: string;
}
"""
    # JavaScript
    js_path = tmp_path / "test.js"
    js_path.write_text(code, encoding="utf-8")
    js_res = analyzer.get_ast_skeleton(str(js_path))
    assert js_res["mode"] == "ast"
    
    js_syms = {s["name"]: s["type"] for s in js_res["symbols"]}
    assert "JSClass" in js_syms
    assert js_syms["JSClass"] in ("class_declaration", "class")
    assert "jsMethod" in js_syms
    assert js_syms["jsMethod"] == "method_definition"
    assert "jsFunc" in js_syms
    assert js_syms["jsFunc"] == "function_declaration"
    assert "arrowFunc" in js_syms
    assert js_syms["arrowFunc"] == "arrow_function"

    # TypeScript
    ts_path = tmp_path / "test.ts"
    ts_path.write_text(code, encoding="utf-8")
    ts_res = analyzer.get_ast_skeleton(str(ts_path))
    assert ts_res["mode"] == "ast"
    ts_syms = {s["name"]: s["type"] for s in ts_res["symbols"]}
    assert "MyInterface" in ts_syms
    assert ts_syms["MyInterface"] == "interface_declaration"

def test_ast_java(analyzer, tmp_path):
    code = """
public class MyJavaClass {
    public MyJavaClass() {}
    public void myJavaMethod() {}
}
"""
    file_path = tmp_path / "test.java"
    file_path.write_text(code, encoding="utf-8")
    res = analyzer.get_ast_skeleton(str(file_path))
    assert res["mode"] == "ast"
    syms = [(s["name"], s["type"]) for s in res["symbols"]]
    assert ("MyJavaClass", "class_declaration") in syms
    assert ("MyJavaClass", "constructor_declaration") in syms
    assert ("myJavaMethod", "method_declaration") in syms

def test_ast_cpp(analyzer, tmp_path):
    code = """
namespace MyNamespace {
    class MyCppClass {};
    struct MyCppStruct {};
    void myCppFunction() {}
}
"""
    file_path = tmp_path / "test.cpp"
    file_path.write_text(code, encoding="utf-8")
    res = analyzer.get_ast_skeleton(str(file_path))
    assert res["mode"] == "ast"
    syms = [(s["name"], s["type"]) for s in res["symbols"]]
    assert ("MyNamespace", "namespace_definition") in syms
    assert ("MyCppClass", "class_specifier") in syms
    assert ("MyCppStruct", "struct_specifier") in syms
    assert ("myCppFunction", "function_definition") in syms

def test_fallback_plain_text(analyzer, tmp_path):
    text_content = "Hello line 1\nHello line 2\n"
    file_path = tmp_path / "test.txt"
    file_path.write_text(text_content, encoding="utf-8")
    
    res = analyzer.get_ast_skeleton(str(file_path))
    assert res["mode"] == "plain-text"
    assert len(res["symbols"]) == 1
    sym = res["symbols"][0]
    assert sym["name"] == "test.txt"
    assert sym["type"] == "file"
    assert sym["start_line"] == 1
    assert sym["end_line"] == 2

def test_file_not_found(analyzer):
    with pytest.raises(FileNotFoundError):
        analyzer.get_ast_skeleton("nonexistent_file.py")

def test_ast_c(analyzer, tmp_path):
    code = """\
struct MyCStruct {
    int x;
    int y;
};

void myCFunction(int a) {
    return;
}
"""
    file_path = tmp_path / "test.c"
    file_path.write_text(code, encoding="utf-8")
    res = analyzer.get_ast_skeleton(str(file_path))
    assert res["mode"] == "ast"
    syms = [(s["name"], s["type"]) for s in res["symbols"]]
    assert ("MyCStruct", "struct_specifier") in syms
    assert ("myCFunction", "function_definition") in syms

def test_ast_go(analyzer, tmp_path):
    code = """\
package main

type MyStruct struct {
    X int
    Y int
}

func myFunction() {
}

func (s *MyStruct) myMethod() {
}
"""
    file_path = tmp_path / "test.go"
    file_path.write_text(code, encoding="utf-8")
    res = analyzer.get_ast_skeleton(str(file_path))
    assert res["mode"] == "ast"
    syms = {s["name"]: s["type"] for s in res["symbols"]}
    assert "MyStruct" in syms
    assert syms["MyStruct"] == "type_spec"
    assert "myFunction" in syms
    assert syms["myFunction"] == "function_declaration"
    assert "myMethod" in syms
    assert syms["myMethod"] == "method_declaration"

def test_ast_rust(analyzer, tmp_path):
    code = """\
struct MyRustStruct {
    x: i32,
    y: i32,
}

enum MyRustEnum {
    A,
    B(i32),
}

trait MyTrait {
    fn trait_method(&self);
}

impl MyRustStruct {
    fn new() -> Self {
        MyRustStruct { x: 0, y: 0 }
    }
}

fn my_rust_function() {}
"""
    file_path = tmp_path / "test.rs"
    file_path.write_text(code, encoding="utf-8")
    res = analyzer.get_ast_skeleton(str(file_path))
    assert res["mode"] == "ast"
    syms = [(s["name"], s["type"]) for s in res["symbols"]]
    assert ("MyRustStruct", "struct_item") in syms
    assert ("MyRustEnum", "enum_item") in syms
    assert ("MyTrait", "trait_item") in syms
    assert ("MyRustStruct", "impl_item") in syms
    assert ("my_rust_function", "function_item") in syms

def test_supported_languages(analyzer):
    """supported_languages returns extensions for all loaded grammars."""
    langs = set(analyzer.supported_languages)
    expected = {".py", ".ts", ".tsx", ".js", ".jsx", ".java",
                ".cpp", ".cc", ".cxx", ".h", ".hpp", ".c", ".go", ".rs"}
    assert expected.issubset(langs)
