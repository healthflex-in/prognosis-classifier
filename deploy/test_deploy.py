"""Run with python3 -m unittest discover -s deploy -p 'test_*.py'. No Docker/network calls."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]


class DeployTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for folder in ('deploy', 'backend/scripts', 'backend/LLM/prognosis', 'bin'):
            (self.root / folder).mkdir(parents=True)
        for relative in ('deploy/deploy.sh', 'backend/scripts/deployment_check.py'):
            shutil.copy(REPO / relative, self.root / relative)
        for target in ('dev', 'prod'):
            shutil.copy(REPO / f'docker-compose.{target}.yml', self.root)
        for name in ('prognosis_agent.py', 'prognosis_langchain_agent.py', 'push_prognosis_to_mongo.py'):
            (self.root / 'backend/LLM/prognosis' / name).write_text('# fixture\n')
        (self.root / 'backend/.env.prod').write_text('# fixture\n')
        (self.root / 'backend/.env.dev').write_text('# fixture\n')
        self.credentials = self.root / 'credentials.json'
        self.credentials.write_text('{}')
        config = {'services': {}}
        for env in ('prod', 'dev'):
            for service in ('backend', 'recommendation'):
                config['services'][f'{service}-{env}'] = {
                    'environment': {'MONGO_URI': 'test-secret', 'MONGO_DB': 'test',
                                    'GOOGLE_APPLICATION_CREDENTIALS': '/app/key.json'},
                    'volumes': [{'source': str(self.credentials), 'target': '/app/key.json'}],
                }
        (self.root / 'config.json').write_text(json.dumps(config))
        docker = self.root / 'bin/docker'
        docker.write_text('''#!/usr/bin/env python3
import json, os, pathlib, sys
root = pathlib.Path(os.environ['DEPLOY_TEST_ROOT'])
args = sys.argv[1:]
with (root / 'calls').open('a') as f: f.write(json.dumps(args) + '\\n')
if 'config' in args: print((root / 'config.json').read_text())
if os.environ.get('FAIL_STAGE') in args: sys.exit(1)
''')
        docker.chmod(0o755)
        self.env = {**os.environ, 'DEPLOY_TEST_ROOT': str(self.root),
                    'PATH': str(self.root / 'bin') + os.pathsep + os.environ['PATH']}

    def run_deploy(self, target='prod'):
        result = subprocess.run(['bash', str(self.root / 'deploy/deploy.sh'), target],
                                env=self.env, capture_output=True, text=True)
        self.assertNotIn('test-secret', result.stdout + result.stderr)
        log = self.root / 'calls'
        calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
        return result, calls

    def test_missing_source_stops_before_docker(self):
        (self.root / 'backend/LLM/prognosis/prognosis_agent.py').unlink()
        result, calls = self.run_deploy()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Missing source', result.stderr)
        self.assertEqual(calls, [])

    def test_missing_env_stops_before_docker(self):
        (self.root / 'backend/.env.prod').unlink()
        result, calls = self.run_deploy()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls, [])

    def test_directory_credentials_never_builds_or_restarts(self):
        self.credentials.unlink()
        self.credentials.mkdir()
        result, calls = self.run_deploy()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any('build' in call or 'up' in call for call in calls))

    def test_missing_credentials_never_created(self):
        self.credentials.unlink()
        result, calls = self.run_deploy()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.credentials.exists())
        self.assertFalse(any('up' in call for call in calls))

    def test_failed_authentication_keeps_running_services(self):
        self.env['FAIL_STAGE'] = 'run'
        result, calls = self.run_deploy()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any('up' in call for call in calls))

    def test_failed_build_keeps_running_services(self):
        self.env['FAIL_STAGE'] = 'build'
        result, calls = self.run_deploy()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any('up' in call for call in calls))

    def test_targets_only_selected_environment_and_waits(self):
        for target in ('dev', 'prod'):
            with self.subTest(target=target):
                (self.root / 'calls').unlink(missing_ok=True)
                result, calls = self.run_deploy(target)
                self.assertEqual(result.returncode, 0, result.stderr)
                for call in calls:
                    self.assertEqual(call[call.index('-f') + 1], str(self.root / f'docker-compose.{target}.yml'))
                up = next(call for call in calls if 'up' in call)
                self.assertEqual(up[-2:], [f'backend-{target}', f'recommendation-{target}'])
                self.assertIn('--wait', up)
                self.assertIn('--no-deps', up)
                self.assertEqual(sum('run' in call for call in calls), 2)
                self.assertFalse(any('down' in call or '--remove-orphans' in call for call in calls))

    def test_other_environment_file_is_not_required(self):
        (self.root / 'backend/.env.dev').unlink()
        result, _ = self.run_deploy('prod')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_unhealthy_deployment_does_not_report_success(self):
        self.env['FAIL_STAGE'] = 'up'
        result, _ = self.run_deploy()
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('Deployment complete', result.stdout)


@unittest.skipUnless(shutil.which('docker'), 'Docker CLI unavailable')
class ComposeIsolationTests(unittest.TestCase):
    """Use the actual Compose parser with dummy env data; no daemon or secrets."""

    def test_each_file_resolves_only_its_environment(self):
        for target, ports in (('dev', (8013, 8014)), ('prod', (8015, 8016))):
            with self.subTest(target=target), tempfile.TemporaryDirectory(prefix='prognosis-compose-') as temp:
                root = Path(temp)
                (root / 'backend').mkdir()
                compose_file = root / f'docker-compose.{target}.yml'
                shutil.copy(REPO / compose_file.name, compose_file)
                (root / f'backend/.env.{target}').write_text(
                    f'MONGO_URI=mongodb://fixture/{target}\nMONGO_DB={target}\n'
                    'GOOGLE_APPLICATION_CREDENTIALS=/app/stance-ai-8919b7295fb6.json\n'
                )
                env = {k: v for k, v in os.environ.items() if not k.startswith(('COMPOSE_', 'DEV_GOOGLE_', 'PROD_GOOGLE_'))}
                result = subprocess.run(['docker', 'compose', '-f', str(compose_file), 'config', '--format', 'json'],
                                        env=env, cwd=root, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                services = json.loads(result.stdout)['services']
                self.assertEqual(set(services), {f'backend-{target}', f'recommendation-{target}'})
                for name, port in zip((f'backend-{target}', f'recommendation-{target}'), ports):
                    self.assertEqual(services[name]['environment']['MONGO_DB'], target)
                    self.assertEqual(int(services[name]['ports'][0]['published']), port)
                    mount = services[name]['volumes'][0]
                    self.assertTrue(mount['read_only'])
                    self.assertFalse(mount['bind']['create_host_path'])


if __name__ == '__main__':
    unittest.main()
