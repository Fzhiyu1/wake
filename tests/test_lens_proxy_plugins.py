import os
import subprocess
import sys
import textwrap
import unittest


class LensProxyPluginDefaultsTest(unittest.TestCase):
    def _import_plugin_names(self, extra_env=None):
        env = os.environ.copy()
        env.pop("LENS_PLUGINS", None)
        if extra_env:
            env.update(extra_env)

        script = textwrap.dedent(
            """
            import sys
            import types

            fastapi = types.ModuleType("fastapi")

            class FastAPI:
                def __init__(self, *args, **kwargs):
                    pass

                def api_route(self, *args, **kwargs):
                    def decorator(func):
                        return func
                    return decorator

            fastapi.FastAPI = FastAPI
            fastapi.Request = object
            sys.modules["fastapi"] = fastapi

            responses = types.ModuleType("fastapi.responses")
            responses.StreamingResponse = object
            responses.Response = object
            sys.modules["fastapi.responses"] = responses

            httpx = types.ModuleType("httpx")
            httpx.AsyncClient = object
            sys.modules["httpx"] = httpx

            uvicorn = types.ModuleType("uvicorn")
            sys.modules["uvicorn"] = uvicorn

            import lens.proxy
            print(lens.proxy.PLUGIN_NAMES)
            """
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
        return result.stdout.strip().splitlines()[-1]

    def test_lens_plugins_default_to_empty_list(self):
        self.assertEqual(self._import_plugin_names(), "[]")

    def test_lens_plugins_can_explicitly_enable_wake_memory(self):
        self.assertEqual(
            self._import_plugin_names({"LENS_PLUGINS": "wake_memory"}),
            "['wake_memory']",
        )


if __name__ == "__main__":
    unittest.main()
