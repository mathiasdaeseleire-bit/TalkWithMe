"""Smart App Control detection and the signed-launcher fallback.

Smart App Control blocks an unsigned, unknown executable outright: there
is no "run anyway" and no exclusion list, and turning it off cannot be
undone without reinstalling Windows. Routing the shortcut through the
signed pythonw.exe is the only way past it that leaves the protection
intact, so the choice has to be made on fact rather than on a guess.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from talkwithme import install as install_mod


def test_state_is_one_of_the_known_values():
    state = install_mod.smart_app_control_state()
    assert state in (None, install_mod.SAC_OFF, install_mod.SAC_ON,
                      install_mod.SAC_EVALUATION), state
    print(f"OK: Smart App Control-stand uitgelezen ({state})")


def test_launcher_points_at_a_signed_python_and_a_real_project():
    found = install_mod.python_launcher()
    if found is None:
        print("OK: geen bruikbare launcher gevonden (verwacht in een losse .exe)")
        return
    pythonw, project = found
    assert os.path.basename(pythonw).lower() == "pythonw.exe", pythonw
    assert os.path.exists(pythonw), "de launcher moet echt bestaan"
    assert os.path.exists(os.path.join(project, "talkwithme", "__main__.py")), \
        "de werkmap moet het pakket bevatten, anders start -m talkwithme niet"
    print("OK: launcher wijst naar pythonw.exe met een werkende projectmap")


def test_launcher_uses_a_windowless_python():
    """python.exe would open a console window on every login."""
    found = install_mod.python_launcher()
    if found is None:
        print("OK: overgeslagen, geen launcher beschikbaar")
        return
    assert "pythonw" in os.path.basename(found[0]).lower(), \
        "python.exe opent een consolevenster; pythonw.exe niet"
    print("OK: de launcher opent geen consolevenster")


def test_install_dir_never_lands_in_a_container():
    assert "\\Packages\\" not in install_mod.INSTALL_DIR, install_mod.INSTALL_DIR
    print("OK: installatiemap ligt buiten een app-container")


if __name__ == "__main__":
    test_state_is_one_of_the_known_values()
    test_launcher_points_at_a_signed_python_and_a_real_project()
    test_launcher_uses_a_windowless_python()
    test_install_dir_never_lands_in_a_container()
    print("\nAlle installatietests geslaagd.")
