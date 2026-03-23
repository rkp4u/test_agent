"""Java-specific AST analysis using tree-sitter."""

import logging

from tree_sitter_language_pack import get_parser

from agent_forge.models.analysis import ClassInfo, FunctionSignature
from agent_forge.tools.analysis.languages.base import LanguageHandler

logger = logging.getLogger(__name__)


class JavaHandler(LanguageHandler):
    """Parses Java source files using tree-sitter."""

    def __init__(self):
        self._parser = get_parser("java")

    def extract_classes(self, source: bytes, file_path: str) -> list[ClassInfo]:
        """Extract Java class declarations with methods, annotations, dependencies."""
        tree = self._parser.parse(source)
        classes = []

        for node in self._find_nodes(tree.root_node, "class_declaration"):
            class_info = self._parse_class(node, source)
            classes.append(class_info)

        return classes

    def extract_functions(self, source: bytes, file_path: str) -> list[FunctionSignature]:
        """Extract all method declarations (flattened from all classes)."""
        classes = self.extract_classes(source, file_path)
        functions = []
        for cls in classes:
            functions.extend(cls.methods)
        return functions

    def extract_imports(self, source: bytes) -> list[str]:
        """Extract import statements."""
        tree = self._parser.parse(source)
        imports = []

        for node in self._find_nodes(tree.root_node, "import_declaration"):
            # Get the full import text, strip 'import ' and ';'
            text = node.text.decode("utf-8").strip()
            text = text.removeprefix("import ").removesuffix(";").strip()
            imports.append(text)

        return imports

    def extract_package(self, source: bytes) -> str:
        """Extract package declaration."""
        tree = self._parser.parse(source)

        for node in self._find_nodes(tree.root_node, "package_declaration"):
            # Find the scoped_identifier child
            for child in node.children:
                if child.type == "scoped_identifier" or child.type == "identifier":
                    return child.text.decode("utf-8")
        return ""

    def _parse_class(self, node, source: bytes) -> ClassInfo:
        """Parse a class_declaration node into ClassInfo."""
        name = ""
        extends = None
        implements = []
        annotations = []
        methods = []
        dependencies = []

        # Get annotations (modifiers node contains annotations)
        for child in node.children:
            if child.type == "modifiers":
                for mod in child.children:
                    if mod.type in ("annotation", "marker_annotation"):
                        ann_text = mod.text.decode("utf-8").strip()
                        annotations.append(ann_text)

            elif child.type == "identifier":
                name = child.text.decode("utf-8")

            elif child.type == "superclass":
                # extends Foo
                for sc in child.children:
                    if sc.type == "type_identifier":
                        extends = sc.text.decode("utf-8")

            elif child.type == "super_interfaces":
                # implements Foo, Bar
                for si in child.children:
                    if si.type == "type_list":
                        for t in si.children:
                            if t.type == "type_identifier":
                                implements.append(t.text.decode("utf-8"))

            elif child.type == "class_body":
                methods = self._parse_class_body(child, name, source)

        # Extract dependencies from field declarations
        dependencies = self._extract_dependencies(node, source)

        # Extract package
        package = self.extract_package(source)

        return ClassInfo(
            name=name,
            package=package,
            extends=extends,
            implements=implements,
            annotations=annotations,
            methods=methods,
            dependencies=dependencies,
        )

    def _parse_class_body(
        self, body_node, class_name: str, source: bytes
    ) -> list[FunctionSignature]:
        """Parse all method declarations in a class body."""
        methods = []

        for node in body_node.children:
            if node.type == "method_declaration":
                method = self._parse_method(node, class_name, source)
                if method:
                    methods.append(method)
            elif node.type == "constructor_declaration":
                method = self._parse_constructor(node, class_name, source)
                if method:
                    methods.append(method)

        return methods

    def _parse_method(
        self, node, class_name: str, source: bytes
    ) -> FunctionSignature | None:
        """Parse a method_declaration node."""
        name = ""
        return_type = "void"
        parameters = []
        visibility = "package-private"
        annotations = []
        complexity = 1  # Base complexity

        for child in node.children:
            if child.type == "modifiers":
                for mod in child.children:
                    if mod.type in ("annotation", "marker_annotation"):
                        annotations.append(mod.text.decode("utf-8").strip())
                    elif mod.type in ("public", "private", "protected"):
                        visibility = mod.text.decode("utf-8")

            elif child.type == "type_identifier" or child.type == "void_type":
                return_type = child.text.decode("utf-8")
            elif child.type == "boolean_type":
                return_type = "boolean"
            elif child.type == "integral_type":
                return_type = child.text.decode("utf-8")
            elif child.type == "generic_type":
                return_type = child.text.decode("utf-8")

            elif child.type == "identifier":
                name = child.text.decode("utf-8")

            elif child.type == "formal_parameters":
                parameters = self._parse_parameters(child)

            elif child.type == "block":
                complexity = self._calculate_complexity(child)

        if not name:
            return None

        return FunctionSignature(
            name=name,
            class_name=class_name,
            parameters=parameters,
            return_type=return_type,
            visibility=visibility,
            annotations=annotations,
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            complexity=complexity,
        )

    def _parse_constructor(
        self, node, class_name: str, source: bytes
    ) -> FunctionSignature | None:
        """Parse a constructor_declaration node."""
        parameters = []
        visibility = "public"
        annotations = []

        for child in node.children:
            if child.type == "modifiers":
                for mod in child.children:
                    if mod.type in ("annotation", "marker_annotation"):
                        annotations.append(mod.text.decode("utf-8").strip())
                    elif mod.type in ("public", "private", "protected"):
                        visibility = mod.text.decode("utf-8")
            elif child.type == "formal_parameters":
                parameters = self._parse_parameters(child)

        return FunctionSignature(
            name=class_name,  # Constructor name = class name
            class_name=class_name,
            parameters=parameters,
            return_type=class_name,
            visibility=visibility,
            annotations=annotations,
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            complexity=1,
        )

    def _parse_parameters(self, params_node) -> list[dict[str, str]]:
        """Parse formal_parameters node into [{name, type}]."""
        parameters = []

        for child in params_node.children:
            if child.type == "formal_parameter":
                param_type = ""
                param_name = ""

                for pc in child.children:
                    if pc.type in (
                        "type_identifier",
                        "integral_type",
                        "boolean_type",
                        "void_type",
                        "generic_type",
                        "array_type",
                        "floating_point_type",
                    ):
                        param_type = pc.text.decode("utf-8")
                    elif pc.type == "identifier":
                        param_name = pc.text.decode("utf-8")

                if param_name:
                    parameters.append({"name": param_name, "type": param_type})

        return parameters

    def _extract_dependencies(self, class_node, source: bytes) -> list[str]:
        """Extract field types as dependencies (for mocking)."""
        deps = []

        for node in self._find_nodes(class_node, "field_declaration"):
            for child in node.children:
                if child.type in ("type_identifier", "generic_type"):
                    dep_type = child.text.decode("utf-8")
                    # Skip primitives and common Java types
                    if dep_type not in ("String", "int", "long", "boolean", "double", "float"):
                        deps.append(dep_type)

        return list(set(deps))  # Deduplicate

    def _calculate_complexity(self, block_node) -> int:
        """Estimate cyclomatic complexity by counting branching statements."""
        complexity = 1  # Base path

        branching_types = {
            "if_statement",
            "for_statement",
            "enhanced_for_statement",
            "while_statement",
            "do_statement",
            "switch_expression",
            "catch_clause",
            "ternary_expression",
            "binary_expression",  # && and || add paths
        }

        def count_branches(node):
            nonlocal complexity
            if node.type in branching_types:
                if node.type == "binary_expression":
                    # Only count && and ||
                    op = None
                    for child in node.children:
                        if child.type in ("&&", "||"):
                            op = child.text.decode("utf-8")
                    if op:
                        complexity += 1
                else:
                    complexity += 1

            for child in node.children:
                count_branches(child)

        count_branches(block_node)
        return complexity

    def _find_nodes(self, root, node_type: str):
        """Recursively find all nodes of a given type."""
        if root.type == node_type:
            yield root
        for child in root.children:
            yield from self._find_nodes(child, node_type)
