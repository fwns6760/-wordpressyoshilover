import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "src" / "yoshilover-gpts-x-actions.php"
OPENAPI = ROOT / "docs" / "openapi" / "yoshilover-gpts-x-actions.openapi.yaml"


def _plugin_source() -> str:
    return PLUGIN.read_text(encoding="utf-8")


def _openapi_source() -> str:
    return OPENAPI.read_text(encoding="utf-8")


def _function_source(src: str, function_name: str) -> str:
    start = src.index(f"function {function_name}")
    next_function = src.find("\nfunction ", start + len(f"function {function_name}"))
    if next_function == -1:
        return src[start:]
    return src[start:next_function]


class GPTsXActionsApiTests(unittest.TestCase):
    def test_registers_only_the_expected_gpts_x_routes(self):
        src = _plugin_source()

        self.assertIn("add_action( 'rest_api_init', 'yoshilover_gpts_x_actions_register_routes' );", src)
        self.assertEqual(src.count("register_rest_route("), 4)
        self.assertIn("'yoshilover/v1'", src)
        self.assertIn("'/x-candidates'", src)
        self.assertIn("'/x-candidates/(?P<id>\\d+)/intent-link'", src)
        self.assertIn("'/x-candidates/(?P<id>\\d+)/posted'", src)
        self.assertIn("'/x-candidates/(?P<id>\\d+)/skip'", src)

        self.assertIn("WP_REST_Server::READABLE", src)
        self.assertGreaterEqual(src.count("WP_REST_Server::CREATABLE"), 3)
        self.assertEqual(src.count("'permission_callback' => 'yoshilover_gpts_x_actions_permission'"), 4)

    def test_permission_callback_requires_authorization_bearer_api_key(self):
        src = _plugin_source()

        self.assertIn("defined( 'YOSHILOVER_GPTS_X_ACTIONS_API_KEY' )", src)
        self.assertIn("constant( 'YOSHILOVER_GPTS_X_ACTIONS_API_KEY' )", src)
        self.assertIn("getenv( 'YOSHILOVER_GPTS_X_ACTIONS_API_KEY' )", src)
        self.assertIn("$request->get_header( 'authorization' )", src)
        self.assertRegex(src, r"Bearer\\s\+")
        self.assertIn("hash_equals( $expected, $provided )", src)
        self.assertNotIn("__return_true", src)

    def test_candidate_query_is_publish_only_and_excludes_closed_meta_statuses(self):
        src = _plugin_source()
        get_candidates = _function_source(src, "yoshilover_gpts_x_actions_get_candidates")

        self.assertIn("'post_status'         => 'publish'", get_candidates)
        self.assertIn("'post_type'           => 'post'", get_candidates)
        self.assertIn("YOSHILOVER_GPTS_X_STATUS_META", get_candidates)
        self.assertIn("'compare' => 'NOT EXISTS'", get_candidates)
        self.assertIn("'value'   => array( 'posted', 'skip' )", get_candidates)
        self.assertIn("'compare' => 'NOT IN'", get_candidates)

    def test_candidate_response_uses_safe_existing_fields_only(self):
        src = _plugin_source()
        build_candidate = _function_source(src, "yoshilover_gpts_x_actions_build_candidate")
        facts_summary = _function_source(src, "yoshilover_gpts_x_actions_get_facts_summary")
        source_url = _function_source(src, "yoshilover_gpts_x_actions_get_source_url")

        for field in (
            "'id'",
            "'title'",
            "'url'",
            "'published_at'",
            "'category'",
            "'facts_summary'",
            "'source_url'",
            "'status'",
        ):
            self.assertIn(field, build_candidate)

        self.assertIn("get_the_excerpt( $post )", facts_summary)
        self.assertNotIn("gemini", facts_summary.lower())
        self.assertNotIn("grok", facts_summary.lower())

        self.assertIn("get_post_meta( $post_id, '_yoshilover_source_url', true )", source_url)
        self.assertIn("get_post_meta( $post_id, 'yl_source_url', true )", source_url)

    def test_intent_link_does_not_update_state_or_call_x_api(self):
        src = _plugin_source()
        intent = _function_source(src, "yoshilover_gpts_x_actions_create_intent_link")

        self.assertIn("'https://x.com/intent/post?text=' . rawurlencode( $text )", intent)
        self.assertNotIn("update_post_meta", intent)

        forbidden_network_markers = (
            "wp_remote_post",
            "wp_remote_get",
            "curl_init",
            "api.twitter.com",
            "api.x.com",
            "statuses/update",
        )
        for marker in forbidden_network_markers:
            self.assertNotIn(marker, src)

    def test_posted_and_skip_only_update_the_approved_post_meta_keys(self):
        src = _plugin_source()
        posted = _function_source(src, "yoshilover_gpts_x_actions_mark_posted")
        skip = _function_source(src, "yoshilover_gpts_x_actions_skip_candidate")

        self.assertIn("update_post_meta( $post->ID, YOSHILOVER_GPTS_X_STATUS_META, 'posted' );", posted)
        self.assertIn("update_post_meta( $post->ID, YOSHILOVER_GPTS_X_POSTED_AT_META, $posted_at );", posted)
        self.assertIn("update_post_meta( $post->ID, YOSHILOVER_GPTS_X_STATUS_META, 'skip' );", skip)
        self.assertIn("update_post_meta( $post->ID, YOSHILOVER_GPTS_X_SKIPPED_AT_META, $skipped_at );", skip)
        self.assertIn("update_post_meta( $post->ID, YOSHILOVER_GPTS_X_SKIP_REASON_META, $reason );", skip)

        self.assertNotIn("wp_update_post", src)
        self.assertNotIn("wp_insert_post", src)
        self.assertNotIn("update_option", src)

    def test_openapi_schema_matches_gpts_actions_auth_and_operation_ids(self):
        spec = _openapi_source()

        self.assertIn("operationId: getXPostCandidates", spec)
        self.assertIn("operationId: createXIntentLink", spec)
        self.assertIn("operationId: markCandidatePosted", spec)
        self.assertIn("operationId: skipCandidate", spec)

        self.assertIn("bearerAuth:", spec)
        self.assertRegex(spec, r"type:\s+http")
        self.assertRegex(spec, r"scheme:\s+bearer")
        self.assertIn('Send the API key as "Authorization: Bearer <key>".', spec)
        self.assertRegex(spec, r"security:\n\s+- bearerAuth: \[\]")

        for path in (
            "/x-candidates:",
            "/x-candidates/{id}/intent-link:",
            "/x-candidates/{id}/posted:",
            "/x-candidates/{id}/skip:",
        ):
            self.assertIn(path, spec)

        for field in (
            "id:",
            "title:",
            "url:",
            "published_at:",
            "category:",
            "facts_summary:",
            "source_url:",
            "status:",
        ):
            self.assertIn(field, spec)


if __name__ == "__main__":
    unittest.main()
