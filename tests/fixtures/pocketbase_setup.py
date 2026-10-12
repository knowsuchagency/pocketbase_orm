import os
import subprocess
import time
import httpx
import signal
import pytest
from pocketbase_orm import PBModel


@pytest.fixture(scope="session")
def pb_client():
    """Fixture to provide an authenticated PocketBase client."""
    username = os.getenv("POCKETBASE_USERNAME", "admin@pb.com")
    password = os.getenv("POCKETBASE_PASSWORD", "mamaistdiebeste")
    url = os.getenv("POCKETBASE_URL", "http://127.0.0.1:4419")

    process = None
    # PocketBase standard health endpoint
    health_endpoint = "/api/health"
    base_url_for_health_check = url.rstrip("/")
    health_check_full_url = f"{base_url_for_health_check}{health_endpoint}"

    try:
        popen_kwargs = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
        }
        if os.name == "posix":
            popen_kwargs["start_new_session"] = True

        process = subprocess.Popen(["just", "reset-pocketbase"], **popen_kwargs)

        time.sleep(1.0)
        if process.poll() is not None:
            stdout_output, stderr_output = process.communicate()
            pytest.fail(f"STDOUT:\n{stdout_output}\nSTDERR:\n{stderr_output}")
        print(f"PocketBase process started (PID: {process.pid}).")

        # --- Health Check using httpx ---
        print(
            f"Performing health check for PocketBase at {health_check_full_url} using httpx..."
        )
        max_retries = 20
        retry_delay_seconds = 1.5
        healthy = False

        health_check_timeout = httpx.Timeout(5)

        with httpx.Client(timeout=health_check_timeout) as http_client:
            for attempt in range(max_retries):
                print(
                    f"Health check attempt {attempt + 1}/{max_retries} to {health_check_full_url}..."
                )
                try:
                    response = http_client.get(health_check_full_url)
                    response.raise_for_status()

                    if response.status_code == 200:
                        print(
                            f"PocketBase reported healthy (HTTP {response.status_code}) on attempt {attempt + 1}."
                        )
                        healthy = True
                        break
                    else:
                        print(
                            f"Health check attempt {attempt + 1}: Received unexpected status {response.status_code}. Expecting 200. Body: {response.text[:200]}"
                        )

                except Exception as e:  # Catch any other unexpected errors
                    print(
                        f"Health check attempt {attempt + 1}: Unexpected error - {type(e).__name__}: {e}"
                    )

                if attempt < max_retries - 1:
                    time.sleep(retry_delay_seconds)
                else:
                    pytest.fail(
                        f"PocketBase did not become healthy at {health_check_full_url} "
                        f"after {max_retries} attempts ({int(max_retries * retry_delay_seconds)} seconds).\n"
                    )

        if not healthy:
            pytest.fail("PocketBase health check definitively failed.")

        print("PocketBase is healthy. Initializing client...")
        client = PBModel.init_client(url, username, password)
        yield client

    finally:
        if process:
            if (
                os.name == "posix"
                and "start_new_session" in popen_kwargs
                and popen_kwargs["start_new_session"]
            ):
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                    print("Sent SIGTERM to process group.")
                except ProcessLookupError:
                    print("Process group already terminated.")
                except Exception as e:
                    print(
                        f"Error sending SIGTERM to process group: {e}. Trying process.terminate()."
                    )
                    process.terminate()
            else:
                process.terminate()
                print("Sent terminate signal to process.")

            try:
                process.wait(timeout=10)
                print("PocketBase process terminated gracefully.")
            except subprocess.TimeoutExpired:
                print(
                    "PocketBase process did not terminate gracefully after 10s. Sending kill signal..."
                )
                if (
                    os.name == "posix"
                    and "start_new_session" in popen_kwargs
                    and popen_kwargs["start_new_session"]
                ):
                    try:
                        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    except Exception as e:
                        print(
                            f"Error sending SIGKILL to process group: {e}. Trying process.kill()."
                        )
                        process.kill()
                else:
                    process.kill()
                try:
                    process.wait(timeout=5)
                except Exception as e:
                    print(f"Error waiting for process after kill: {e}")
            except Exception as e:
                print(f"Error during process wait: {e}")

            try:
                # Best effort to get any final output
                stdout_output, stderr_output = process.communicate(timeout=1)
                if stdout_output:
                    print(f"Final PocketBase STDOUT:\n{stdout_output.strip()}")
                if stderr_output:
                    print(f"Final PocketBase STDERR:\n{stderr_output.strip()}")
            except Exception as e:
                print(f"Error reading stdout/stderr from process: {e}")
