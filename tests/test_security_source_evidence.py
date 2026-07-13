from __future__ import annotations

import json
from pathlib import Path

from quality_runner.security.candidates import security_candidate_fingerprint
from quality_runner.workflow import run_payload
from test_support.quality_runner_fixtures import write_js_fixture
from test_support.security_scan import run_security_scan as _run_scan


def test_secret_source_analysis_handles_multiline_prefix_and_triple_values() -> None:
    from quality_runner.evidence_redaction import (
        SecretAssignmentSpan,
        analyze_secret_like_source_lines,
    )

    markers = {
        "split": "m7-split-operator-secret-marker-42",
        "api_key_value": "m7-api-key-value-secret-marker-42",
        "secret_value": "m7-secret-value-secret-marker-42",
        "password_value": "m7-password-value-secret-marker-42",
        "triple": "m7-triple-value-secret-marker-42",
    }
    lines = [
        "const apiKey",
        f'  = "{markers["split"]}";',
        f'const apiKeyValue = "{markers["api_key_value"]}";',
        f'const secretValue = "{markers["secret_value"]}";',
        f'const passwordValue = "{markers["password_value"]}";',
        'const tokenizer = "tokenizer-stays-visible";',
        'const secretary = "secretary-stays-visible";',
        'const label = "apiKey";',
        'const ordinary = "ordinary-stays-visible";',
        "// secretValue",
        'const another = "another-stays-visible";',
        'private_key = """',
        f"{markers['triple']} eval(userInput)",
        '"""',
    ]

    analysis = analyze_secret_like_source_lines(lines)
    redacted_text = "\n".join(analysis.lines)

    assert len(analysis.lines) == len(lines)
    assert analysis.assignment_spans == [
        SecretAssignmentSpan(start_line=1, end_line=2),
        SecretAssignmentSpan(start_line=3, end_line=3),
        SecretAssignmentSpan(start_line=4, end_line=4),
        SecretAssignmentSpan(start_line=5, end_line=5),
        SecretAssignmentSpan(start_line=12, end_line=14),
    ]
    assert all(marker not in redacted_text for marker in markers.values())
    assert analysis.lines[5:11] == lines[5:11]


def test_multiline_secret_candidates_redact_all_artifacts_and_keep_line_attribution(
    tmp_path: Path,
) -> None:
    write_js_fixture(tmp_path)
    markers = {
        "split": "m7-split-artifact-secret-marker-42",
        "prefix": "m7-prefix-artifact-secret-marker-42",
        "route": "m7-route-artifact-secret-marker-42",
        "triple": "m7-triple-artifact-secret-marker-42",
    }
    src = tmp_path / "src"
    src.mkdir()
    (src / "multiline-secrets.js").write_text(
        "\n".join(
            [
                "const apiKey",
                (f'  = "{markers["split"]}"; const splitState = one ? two : three ? four : five;'),
                (
                    f'const apiKeyValue = "{markers["prefix"]}"; '
                    "const prefixState = one ? two : three ? four : five;"
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (src / "python-secret.py").write_text(
        "\n".join(
            [
                'private_key = """',
                f"{markers['triple']} eval(userInput)",
                '"""',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    route = tmp_path / "app" / "api" / "chat" / "route.ts"
    route.parent.mkdir(parents=True)
    route.write_text(
        "\n".join(
            [
                "const apiKey",
                f'  = "{markers["route"]}"; await openai.chat.completions.create({{}});',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    payload = run_payload(repo_root=tmp_path, run_id="multiline-secret-candidates-001")
    security_scan = json.loads(
        Path(payload["artifact_paths"]["security_scan_json"]).read_text(encoding="utf-8")
    )
    secret_candidates = [
        item for item in security_scan["candidates"] if item["category"] == "secrets-exposure"
    ]
    split_candidate = next(
        item
        for item in secret_candidates
        if item["file"] == "src/multiline-secrets.js" and item["line"] == 1
    )
    prefix_candidate = next(
        item
        for item in secret_candidates
        if item["file"] == "src/multiline-secrets.js" and item["line"] == 3
    )
    triple_candidate = next(
        item
        for item in secret_candidates
        if item["file"] == "src/python-secret.py" and item["line"] == 1
    )
    dangerous_sink = next(
        item
        for item in security_scan["candidates"]
        if item["category"] == "dangerous-sink" and item["file"] == "src/python-secret.py"
    )
    expensive_api = next(
        item
        for item in security_scan["candidates"]
        if item["category"] == "expensive-api-abuse" and item["file"] == "app/api/chat/route.ts"
    )

    assert split_candidate["evidence"] == (
        'const apiKey = "<redacted>"; const splitState = one ? two : three ? four : five;'
    )
    assert prefix_candidate["evidence"] == (
        'const apiKeyValue = "<redacted>"; const prefixState = one ? two : three ? four : five;'
    )
    assert '"<redacted>"' in triple_candidate["evidence"]
    assert markers["triple"] not in dangerous_sink["evidence"]
    assert markers["route"] not in expensive_api["evidence"]
    artifact_texts = [
        path.read_text(encoding="utf-8")
        for path in (
            tmp_path / ".quality-runner" / "runs" / "multiline-secret-candidates-001"
        ).rglob("*")
        if path.is_file()
    ]
    assert all(marker not in text for marker in markers.values() for text in artifact_texts)


def test_complex_secret_contexts_never_persist_source_literals(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)
    markers = {
        "semicolon_first": "m7-semicolon-first-secret-marker-42",
        "semicolon_second": "m7-semicolon-second-secret-marker-42",
        "url_first": "m7-url-first-secret-marker-42",
        "url_second": "m7-url-second-secret-marker-42",
        "comment": "m7-comment-secret-marker-42",
        "callee": "m7-callee-secret-marker-42",
        "regex": "m7-regex-secret-marker-42",
        "object": "m7-object-secret-marker-42",
        "bracket": "m7-bracket-secret-marker-42",
        "fallback": "m7-fallback-secret-marker-42",
    }
    src = tmp_path / "src"
    src.mkdir()
    (src / "complex-secrets.js").write_text(
        "\n".join(
            [
                "const semicolonKey = (",
                f'  "{markers["semicolon_first"]}" +',
                (
                    f'  "{markers["semicolon_second"]}"; '
                    "const semicolonState = one ? two : three ? four : five;"
                ),
                ");",
                "const urlKey = (",
                f'  "https://{markers["url_first"]}" +',
                (f'  "{markers["url_second"]}"; const urlState = one ? two : three ? four : five;'),
                ");",
                "const commentKey =",
                '  /* quoted " metadata */',
                (
                    f'  "{markers["comment"]}"; '
                    "const commentState = one ? two : three ? four : five;"
                ),
                "const callKey =",
                "  String",
                "  (",
                f'  "{markers["callee"]}"',
                "  ); const callState = one ? two : three ? four : five;",
                f'const regexKey = /"/.source + "{markers["regex"]}"; eval(userInput);',
                f'const config = {{ "apiKey": "{markers["object"]}" }}; eval(userInput);',
                f'config["apiKey"] = "{markers["bracket"]}"; eval(userInput);',
                "const configFallback = process.env.API_KEY ??",
                f'  "{markers["fallback"]}"; eval(userInput);',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    payload = run_payload(repo_root=tmp_path, run_id="complex-secret-contexts-001")
    security_scan = json.loads(
        Path(payload["artifact_paths"]["security_scan_json"]).read_text(encoding="utf-8")
    )
    artifact_texts = [
        path.read_text(encoding="utf-8")
        for path in (tmp_path / ".quality-runner" / "runs" / "complex-secret-contexts-001").rglob(
            "*"
        )
        if path.is_file()
    ]

    assert "secret-in-fallback" in {item["category"] for item in security_scan["candidates"]}
    assert all(marker not in text for marker in markers.values() for text in artifact_texts)


def test_source_redaction_fails_closed_for_language_specific_literal_syntax(
    tmp_path: Path,
) -> None:
    write_js_fixture(tmp_path)
    markers = {
        "escaped_identifier": "m7-js-escaped-identifier-marker-123",
        "escaped_key": "m7-js-escaped-key-marker-123",
        "url_escaped_identifier": "m21-url-comment-heuristic-marker-123",
        "regex_escaped_identifier": "m21-regex-comment-heuristic-marker-123",
        "multiline_object_key": "m24-json-multiline-key-marker-123",
        "template_key": "m7-js-template-key-marker-123",
        "dynamic_template_key": "m7-js-dynamic-template-key-marker-123",
        "concatenated_key": "m7-js-concatenated-key-marker-123",
        "identity_escaped_key": "m7-js-identity-escaped-key-marker-123",
        "octal_escaped_key": "m7-js-octal-escaped-key-marker-123",
        "unmatched_regex_assignment": "m35-regex-unmatched-quote-marker-123",
        "paired_regex_assignment": "m36-regex-prefix-marker-123",
        "return_regex": "m7-js-return-regex-marker-123",
        "nested_template": "m7-js-nested-template-marker-123",
        "nested_template_semicolon": "m7-js-nested-template-semicolon-marker-123",
        "nested_template_multiline": "m7-js-nested-template-multiline-marker-123",
        "nested_template_inner_multiline": "m7-js-nested-template-inner-multiline-marker-123",
        "regex": "m7-js-regex-marker-123",
        "comment": "m7-js-comment-marker-123",
        "log": "m7-js-log-marker-123",
        "nested_log": "m7-js-nested-log-marker-123",
        "floor_division": "m7-python-floor-division-marker-123",
        "continuation": "m7-python-continuation-marker-123",
        "parenthesized_key": "m7-python-parenthesized-key-marker-123",
        "raw_key": "m7-python-raw-key-marker-123",
        "formatted_key": "m7-python-formatted-key-marker-123",
        "adjacent_key": "m7-python-adjacent-key-marker-123",
        "fullwidth_key": "m7-python-fullwidth-key-marker-123",
        "fstring": "m7-python-fstring-marker-123",
        "raw_formatted_fstring": "m7-python-rf-fstring-marker-123",
        "yaml": "m7-yaml-folded-marker-123",
    }
    src = tmp_path / "src"
    src.mkdir()
    (src / "lexer-edge.js").write_text(
        "\n".join(
            [
                f'const api\\u{{004B}}eyValue = "{markers["escaped_identifier"]}"; eval(userInput);',
                (
                    f'const config = {{ "api\\u{{004b}}ey": "{markers["escaped_key"]}" }}; '
                    "eval(userInput);"
                ),
                'const url = "https://example.test"; const api\\u004bey = "'
                + markers["url_escaped_identifier"]
                + '"; eval(userInput);',
                'const pattern = /\\//; const api\\u004bey = "'
                + markers["regex_escaped_identifier"]
                + '"; eval(userInput);',
                "{",
                '  "apiKey":',
                f'  "{markers["multiline_object_key"]}", "dangerouslySetInnerHTML": true,',
                "}",
                f'config[`apiKey`] = "{markers["template_key"]}"; eval(userInput);',
                'config[`api${"Key"}`] = "'
                + markers["dynamic_template_key"]
                + '"; eval(userInput);',
                'config["api" + "Key"] = "' + markers["concatenated_key"] + '"; eval(userInput);',
                'config["api\\Key"] = "' + markers["identity_escaped_key"] + '"; eval(userInput);',
                'config[\\141piKey] = "' + markers["octal_escaped_key"] + '"; eval(userInput);',
                "const apiKey = /"
                + markers["unmatched_regex_assignment"]
                + '"/.source; eval(userInput);',
                "const apiKey = /"
                + markers["paired_regex_assignment"]
                + '"metadata"/.source; eval(userInput);',
                (
                    f'const returnKey = (() => {{ return /"/.source + "{markers["return_regex"]}"; '
                    "})(); eval(userInput);"
                ),
                f"const templateKey = `${{`{markers['nested_template']}`}}`; eval(userInput);",
                "const nestedKey = `${`prefix; "
                + markers["nested_template_semicolon"]
                + "`}`; eval(userInput);",
                "const multilineKey = `${`prefix` +",
                "  `" + markers["nested_template_multiline"] + "`",
                "`}`; eval(userInput);",
                "const innerMultilineKey = `${`prefix",
                markers["nested_template_inner_multiline"] + "`}`; eval(userInput);",
                f'const regexKey = /"{markers["regex"]}"/.source; eval(userInput);',
                (f'const commentKey = /* "{markers["comment"]}" */ getValue(); eval(userInput);'),
                f'console.log(/"/.source + "{markers["log"]}", token);',
                "console.log(`${`" + markers["nested_log"] + "`}`, token);",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (src / "lexer_edge.py").write_text(
        "\n".join(
            [
                f'api_key_value = source // "{markers["floor_division"]}"; eval(user_input)',
                'api_key_value = "prefix" \\',
                f'    "{markers["continuation"]}"; eval(user_input)',
                f'config = {{("api_key"): "{markers["parenthesized_key"]}"}}; eval(user_input)',
                f'config = {{r"api_key": "{markers["raw_key"]}"}}; eval(user_input)',
                f'config = {{f"api_key": "{markers["formatted_key"]}"}}; eval(user_input)',
                f'config = {{"api" "_key": "{markers["adjacent_key"]}"}}; eval(user_input)',
                f'apiｋeyValue = "{markers["fullwidth_key"]}"; eval(user_input)',
                f'api_key_value = f"{{ "{markers["fstring"]}" }}"; eval(user_input)',
                f'api_key_value = rf"{{ "{markers["raw_formatted_fstring"]}" }}"; eval(user_input)',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (src / "lexer-edge.yaml").write_text(
        "\n".join(
            [
                'api_key: "prefix-long',
                f'  {markers["yaml"]} eval(userInput)"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    run_payload(repo_root=tmp_path, run_id="language-literal-redaction-001")
    artifact_texts = [
        path.read_text(encoding="utf-8")
        for path in (
            tmp_path / ".quality-runner" / "runs" / "language-literal-redaction-001"
        ).rglob("*")
        if path.is_file()
    ]

    assert all(marker not in text for marker in markers.values() for text in artifact_texts)


def test_tokenless_secret_values_are_redacted_across_generated_artifacts(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)
    markers = {
        "yaml_plain": "m14-yaml-plain-secret-marker-123",
        "yaml_block": "m14-yaml-block-secret-marker-123",
        "yaml_folded": "m14-yaml-folded-secret-marker-123",
        "shell": "m15-shell-bare-secret-marker-123",
        "quoted_shell": "m29-shell-quoted-assignment-marker-123",
    }
    src = tmp_path / "src"
    src.mkdir()
    (src / "secrets.yaml").write_text(
        "\n".join(
            [
                f"api_key: {markers['yaml_plain']} eval(userInput)",
                "api_key: |",
                f"  {markers['yaml_block']} eval(userInput)",
                "api_key: >",
                f"  {markers['yaml_folded']} eval(userInput)",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (src / "secrets.sh").write_text(
        "\n".join(
            [
                f"export API_KEY={markers['shell']}; dangerouslySetInnerHTML=1",
                f'export "API_KEY={markers["quoted_shell"]}"; dangerouslySetInnerHTML=1',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    run_payload(repo_root=tmp_path, run_id="tokenless-secret-redaction-001")
    artifact_texts = [
        path.read_text(encoding="utf-8")
        for path in (
            tmp_path / ".quality-runner" / "runs" / "tokenless-secret-redaction-001"
        ).rglob("*")
        if path.is_file()
    ]

    assert all(marker not in text for marker in markers.values() for text in artifact_texts)


def test_nested_templates_ignore_regex_and_comment_braces(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)
    markers = {
        "regex": "m16-template-regex-brace-marker-123",
        "character_class": "m16-template-character-class-marker-123",
        "comment": "m16-template-comment-brace-marker-123",
        "split_template": "m22-split-log-marker-123",
        "split_literal": "m23-split-log-literal-marker-123",
    }
    src = tmp_path / "src"
    src.mkdir()
    (src / "templates.js").write_text(
        "\n".join(
            [
                "const apiKey = `${/}/.test(value) ? `prefix` +",
                f"  `{markers['regex']}`",
                '` : ""}`; eval(userInput);',
                "const apiKey = `${/[}]/.test(value) ? `prefix` +",
                f"  `{markers['character_class']}`",
                '` : ""}`; eval(userInput);',
                "const apiKey = `${/* } */ true ? `prefix` +",
                f"  `{markers['comment']}`",
                '` : ""}`; eval(userInput);',
                "console.log(`${`prefix` +",
                f"  `{markers['split_template']}`",
                "`}`, apiKey); eval(userInput);",
                "console.log(",
                "  apiKey,",
                f'  "{markers["split_literal"]}"); eval(userInput);',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    run_payload(repo_root=tmp_path, run_id="template-brace-redaction-001")
    artifact_texts = [
        path.read_text(encoding="utf-8")
        for path in (tmp_path / ".quality-runner" / "runs" / "template-brace-redaction-001").rglob(
            "*"
        )
        if path.is_file()
    ]

    assert all(marker not in text for marker in markers.values() for text in artifact_texts)


def test_newly_redacted_multiline_sink_evidence_migrates_its_fingerprint(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)
    marker = "m7-new-split-secret-marker-12345"
    src = tmp_path / "src"
    src.mkdir()
    (src / "split.js").write_text(
        "\n".join(["const apiKey", f' = "{marker}"; eval(userInput);']) + "\n",
        encoding="utf-8",
    )

    candidates = _run_scan(tmp_path)["candidates"]
    dangerous_sink = next(
        item
        for item in candidates
        if item["file"] == "src/split.js" and item["category"] == "dangerous-sink"
    )
    raw_evidence = f'= "{marker}"; eval(userInput);'

    assert marker not in dangerous_sink["evidence"]
    assert dangerous_sink["fingerprint"] != security_candidate_fingerprint(
        category="dangerous-sink",
        file="src/split.js",
        line=2,
        evidence=raw_evidence,
    )


def test_source_redaction_preserves_input_cardinality_and_log_redaction() -> None:
    from quality_runner.evidence_redaction import redact_secret_like_source_lines

    marker = "m7-public-helper-log-marker-123"
    lines = [
        f'console.log("{marker}", apiKey);',
        'const apiKey = "m7-cardinality-marker-123";\nconst label = "kept";',
        'api_key_value = source // "m7-floor-division-marker-123"; eval(user_input)',
        "api_key_value = source // apiKey; eval(user_input)",
        "api_key_value = source//apiKey; eval(user_input)",
    ]

    redacted = redact_secret_like_source_lines(lines)

    assert len(redacted) == len(lines)
    assert marker not in redacted[0]
    assert 'const apiKey = "<redacted>";\nconst label = "kept";' == redacted[1]
    assert 'api_key_value = source // "<redacted>"; eval(user_input)' == redacted[2]
    assert "api_key_value = source // apiKey; eval(user_input)" == redacted[3]
    assert "api_key_value = source//apiKey; eval(user_input)" == redacted[4]


def test_malformed_log_contexts_do_not_rescan_the_remaining_source() -> None:
    from time import perf_counter

    from quality_runner.evidence_redaction import redact_secret_like_source_lines

    started = perf_counter()
    redact_secret_like_source_lines(
        [
            *(['console.log(apiKey, "ordinary"'] * 1_000),
            "[" * 5_000,
            ":" * 5_000,
            "http://" * 5_000,
        ]
    )

    assert perf_counter() - started < 1


def test_source_redaction_fails_closed_for_adversarial_lexer_contexts(tmp_path: Path) -> None:
    from quality_runner.evidence_redaction import redact_secret_like_source_lines

    write_js_fixture(tmp_path)
    markers = {
        "private_field": "m41-private-field-secret-marker-123",
        "static_private_field": "m41-static-private-field-secret-marker-123",
        "accessor_private_field": "m41-accessor-private-field-secret-marker-123",
        "nested_outer_private_field": "m41-nested-outer-private-field-secret-marker-123",
        "regex": "m42-raw-regex-secret-marker-123",
        "fallback": "m42-fallback-regex-secret-marker-123",
        "comment": "m43-comment-rhs-secret-marker-123",
        "multiline_log": "m44-multiline-log-secret-marker-123",
        "nested_log": "m45-nested-log-secret-marker-123",
        "raw_log": "m45-raw-log-regex-secret-marker-123",
        "computed_log": "m46-computed-log-secret-marker-123",
        "optional_computed_log": "m46-optional-computed-log-secret-marker-123",
        "computed_optional_call": "m46-computed-optional-call-secret-marker-123",
        "logger_computed": "m46-logger-computed-secret-marker-123",
        "template": "m47-template-division-secret-marker-123",
        "heredoc": "m48-heredoc-secret-marker-123",
        "docker": "m49-docker-env-secret-marker-123",
        "header_comment": "m50-comment-header-artifact-marker-123",
        "malformed_assignment": "m51-malformed-assignment-secret-marker-123",
        "malformed_log": "m52-malformed-log-secret-marker-123",
        "bare_object": "m53-bare-object-key-secret-marker-123",
    }
    lines = [
        "const harmless = 1 // apiKey =",
        '"comment-triggered-long-string-12345";',
        "class C {",
        f"  #apiKey = {markers['private_field']}; eval(userInput);",
        f"  static #apiKey = {markers['static_private_field']}; eval(userInput);",
        f"  accessor #apiKey = {markers['accessor_private_field']}; eval(userInput);",
        "}",
        "class Outer {",
        "  static Inner = class { #inner = value; };",
        f"  #apiKey = {markers['nested_outer_private_field']}; eval(userInput);",
        "}",
        f"const apiKey = /{markers['regex']}/; eval(userInput);",
        f"const value = apiKey ?? /{markers['fallback']}/; eval(userInput);",
        f'const apiKey = /* {markers["comment"]} "metadata" */ "value"; eval(userInput);',
        "console.log(",
        "  apiKey,",
        f'  "{markers["multiline_log"]}"); eval(userInput);',
        "console.log(`${`prefix-" + markers["nested_log"] + "`}`, apiKey); eval(userInput);",
        "console.log(apiKey, /" + markers["raw_log"] + "/); eval(userInput);",
        'console["log"]("' + markers["computed_log"] + '", apiKey); eval(userInput);',
        'console?.["log"]("' + markers["optional_computed_log"] + '", apiKey); eval(userInput);',
        'console["log"]?.("' + markers["computed_optional_call"] + '", apiKey); eval(userInput);',
        'logger["info"]("' + markers["logger_computed"] + '", apiKey); eval(userInput);',
        "console /* "
        + markers["header_comment"]
        + ' */ . log("ordinary", apiKey); eval(userInput);',
        "const apiKey = `${a / /[}]/.source.length ? `prefix-"
        + markers["template"]
        + '` : ""}`; eval(userInput);',
        "export API_KEY=$(cat <<'EOF'",
        markers["heredoc"],
        "EOF",
        "); eval(userInput);",
        f"ENV API_KEY {markers['docker']} eval(userInput)",
        f"const apiKey = /{markers['malformed_assignment']}; eval(userInput);",
        "console.log(apiKey, /" + markers["malformed_log"] + "; eval(userInput);",
        f"const config = {{ apiKey: /{markers['bare_object']}/ }}; eval(userInput);",
    ]
    src = tmp_path / "src"
    src.mkdir()
    (src / "adversarial.js").write_text("\n".join(lines) + "\n", encoding="utf-8")

    redacted = "\n".join(redact_secret_like_source_lines(lines))
    payload = run_payload(repo_root=tmp_path, run_id="adversarial-lexer-redaction-001")
    security_scan = json.loads(
        Path(payload["artifact_paths"]["security_scan_json"]).read_text(encoding="utf-8")
    )
    artifact_texts = [
        path.read_text(encoding="utf-8")
        for path in (
            tmp_path / ".quality-runner" / "runs" / "adversarial-lexer-redaction-001"
        ).rglob("*")
        if path.is_file()
    ]

    assert all(marker not in redacted for marker in markers.values())
    assert 'console["log"]("<redacted>", apiKey);' in redacted
    assert not any(
        item["category"] == "secrets-exposure" and item["line"] == 1
        for item in security_scan["candidates"]
    )
    assert all(marker not in text for marker in markers.values() for text in artifact_texts)


def test_secret_parser_keeps_parameter_references_out_of_assignment_candidates(
    tmp_path: Path,
) -> None:
    write_js_fixture(tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    (src / "parameter.js").write_text(
        "\n".join(
            [
                "function f(apiKey) {",
                '  value = "harmless-long-string-12345";',
                "  eval(userInput);",
                "}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    candidates = [
        item for item in _run_scan(tmp_path)["candidates"] if item["file"] == "src/parameter.js"
    ]

    assert [(item["category"], item["line"]) for item in candidates] == [("dangerous-sink", 3)]


def test_comment_syntax_does_not_create_secret_assignment_candidates(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    (src / "comments.js").write_text(
        "\n".join(
            [
                "const harmless = 1; // apiKey =",
                '"comment-triggered-long-string-12345";',
                "const called = fn() // apiKey =",
                '"comment-after-call-long-string-12345";',
                "const value = item // apiKey =",
                '"comment-after-identifier-long-string-12345";',
                "const number = 1 // apiKey =",
                '"comment-after-number-long-string-12345";',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (src / "comments.py").write_text(
        "\n".join(
            [
                "value=1#apiKey =",
                '"comment-triggered-long-string-12345"',
                '#apiKey = "comment-without-space-long-string-12345"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    assert not _run_scan(tmp_path)["candidates"]


def test_legacy_structured_literal_evidence_is_preserved(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    (src / "x.js").write_text(
        "\n".join(
            [
                'const apiKey = /"legacy-regex-secret-marker-12345"/.source;',
                'const apiKey /* "quoted metadata" */ = "legacy-comment-secret-marker-12345";',
                'console.log(/foo"bar/, token);',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (src / "x.py").write_text(
        "\n".join(
            [
                'api_key = f"legacy-fstring-secret-marker-12345"',
                'api_key = f"m7-fstring-prefix-{value}-secret-suffix-12345"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    candidates = _run_scan(tmp_path)["candidates"]
    regex = next(
        item
        for item in candidates
        if item["file"] == "src/x.js"
        and item["line"] == 1
        and item["category"] == "secrets-exposure"
    )
    comment = next(
        item
        for item in candidates
        if item["file"] == "src/x.js"
        and item["line"] == 2
        and item["category"] == "secrets-exposure"
    )
    fstring = next(
        item
        for item in candidates
        if item["file"] == "src/x.py"
        and item["line"] == 1
        and item["category"] == "secrets-exposure"
    )
    interpolated_fstring = next(
        item
        for item in candidates
        if item["file"] == "src/x.py"
        and item["line"] == 2
        and item["category"] == "secrets-exposure"
    )
    unmatched_regex = next(
        item
        for item in candidates
        if item["file"] == "src/x.js" and item["line"] == 3 and item["category"] == "secret-in-log"
    )

    assert regex["evidence"] == 'const apiKey = /"<redacted>"/.source;'
    assert comment["evidence"] == 'const apiKey /* "<redacted>" */ = "<redacted>";'
    assert fstring["evidence"] == 'api_key = f"<redacted>"'
    assert interpolated_fstring["evidence"] == 'api_key = f"<redacted>"'
    assert unmatched_regex["evidence"] == 'console.log(/foo"bar/, token);'


def test_existing_security_candidate_evidence_contracts_stay_stable(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    (src / "x.js").write_text(
        "\n".join(
            [
                'const x = { "apiKey": "existing-object-secret-123" }; eval(userInput);',
                'const fallback = process.env.API_KEY ?? "existing-fallback-secret-123"; '
                'const label = "kept";',
                'console.log("existing-log-secret-123", token);',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    candidates = [item for item in _run_scan(tmp_path)["candidates"] if item["file"] == "src/x.js"]
    dangerous_sink = next(item for item in candidates if item["category"] == "dangerous-sink")
    fallback = next(item for item in candidates if item["category"] == "secret-in-fallback")
    log = next(item for item in candidates if item["category"] == "secret-in-log")

    assert (
        dangerous_sink["evidence"] == 'const x = { "<redacted>": "<redacted>" }; eval(userInput);'
    )
    assert dangerous_sink["fingerprint"] == "sec-80ffbb2a7f208385"
    assert fallback["evidence"] == (
        'const fallback = process.env.API_KEY ?? "<redacted>"; const label = "<redacted>";'
    )
    assert log["evidence"] == 'console.log("<redacted>", token);'


def test_disabled_secrets_keeps_legacy_dangerous_sink_suppression(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)
    (tmp_path / ".quality-runner.toml").write_text(
        "\n".join(["[quality_runner.security]", 'disabled_rule_groups = ["secrets"]', ""]),
        encoding="utf-8",
    )
    src = tmp_path / "src"
    src.mkdir()
    (src / "disabled.js").write_text(
        'const secret = "disabled-group-marker-123"; eval(userInput);\n',
        encoding="utf-8",
    )

    assert not _run_scan(tmp_path)["candidates"]


def test_split_live_secret_candidates_keep_high_confidence(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    (src / "split-live.js").write_text(
        "\n".join(["const apiKey", '  = "sk_live_m7_high_confidence_marker_123";']) + "\n",
        encoding="utf-8",
    )

    candidate = next(
        item
        for item in _run_scan(tmp_path)["candidates"]
        if item["file"] == "src/split-live.js" and item["category"] == "secrets-exposure"
    )

    assert candidate["confidence"] == "high"


def test_legacy_security_candidate_identity_is_preserved(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    (src / "legacy.js").write_text(
        "\n".join(
            [
                "eval(userInput);",
                'const apiKey = "existing-secret-value-123";',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    candidates = _run_scan(tmp_path)["candidates"]
    relevant = [item for item in candidates if item["file"] == "src/legacy.js"]

    assert [(item["id"], item["category"], item["line"]) for item in relevant] == [
        ("SEC-dangerous_sink-0001", "dangerous-sink", 1),
        ("SEC-secrets_exposure-0002", "secrets-exposure", 2),
    ]
    assert relevant[1]["evidence"] == 'const apiKey = "<redacted>";'
    assert relevant[1]["fingerprint"] == security_candidate_fingerprint(
        category="secrets-exposure",
        file="src/legacy.js",
        line=2,
        evidence='const apiKey = "<redacted>";',
    )


def test_legacy_multiline_secret_fingerprint_is_preserved(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    (src / "legacy-multiline.js").write_text(
        "\n".join(
            [
                'const apiKey = "existing-secret-long-abcdef" +',
                '  "existing-secret-continuation-uvwxyz";',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    candidates = [
        item
        for item in _run_scan(tmp_path)["candidates"]
        if item["file"] == "src/legacy-multiline.js" and item["category"] == "secrets-exposure"
    ]

    assert len(candidates) == 1
    assert candidates[0]["line"] == 1
    assert candidates[0]["evidence"] == 'const apiKey = "<redacted>" +'
    assert candidates[0]["fingerprint"] == security_candidate_fingerprint(
        category="secrets-exposure",
        file="src/legacy-multiline.js",
        line=1,
        evidence='const apiKey = "<redacted>" +',
    )


def test_disabling_secrets_suppresses_multiline_span_candidates(tmp_path: Path) -> None:
    write_js_fixture(tmp_path)
    (tmp_path / ".quality-runner.toml").write_text(
        "\n".join(
            [
                "[quality_runner.security]",
                'disabled_rule_groups = ["secrets"]',
                "",
            ]
        ),
        encoding="utf-8",
    )
    src = tmp_path / "src"
    src.mkdir()
    (src / "split-secret.js").write_text(
        "\n".join(
            [
                "const apiKey",
                '  = "disabled-group-secret-marker-42";',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    categories = {item["category"] for item in _run_scan(tmp_path)["candidates"]}

    assert "secrets-exposure" not in categories
