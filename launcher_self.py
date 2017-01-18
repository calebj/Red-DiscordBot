from launcher import *

INTRO = ("======================\n"
         "Red SelfBot - Launcher\n"
         "======================\n")

args = parse_cli_arguments()

def run_red(autorestart):
    interpreter = sys.executable

    if interpreter is None: # This should never happen
        raise RuntimeError("Couldn't find Python's interpreter")

    if verify_requirements() is None:
        print("You don't have the requirements to start Red. "
              "Install them from the launcher.")
        if not INTERACTIVE_MODE:
            exit(1)

    cmd = (interpreter, "red_self.py")

    while True:
        try:
            code = subprocess.call(cmd)
        except KeyboardInterrupt:
            code = 0
            break
        else:
            if code == 0:
                break
            elif code == 26:
                print("Restarting Red selfbot...")
                continue
            else:
                if not autorestart:
                    break

    print("Red selfbot has been terminated. Exit code: %d" % code)

    if INTERACTIVE_MODE:
        wait()

def main():
    print("Verifying git installation...")
    has_git = is_git_installed()
    is_git_installation = os.path.isdir(".git")
    if IS_WINDOWS:
        os.system("TITLE Red SelfBot - Launcher")
    clear_screen()

    try:
        create_fast_start_scripts()
    except Exception as e:
        print("Failed making fast start scripts: {}\n".format(e))

    while True:
        print(INTRO)

        if not is_git_installation:
            print("WARNING: It doesnt' look like Red has been "
                  "installed with git.\nThis means that you won't "
                  "be able to update and some features won't be working.\n"
                  "A reinstallation is recommended. Follow the guide "
                  "properly this time:\n"
                  "https://twentysix26.github.io/Red-Docs/\n")

        if not has_git:
            print("WARNING: Git not found. This means that it's either not "
                  "installed or not in the PATH environment variable like "
                  "requested in the guide.\n")

        print("1. Run Red selfbot /w autorestart in case of issues")
        print("2. Run Red selfbot")
        print("3. Update")
        print("4. Install requirements")
        print("5. Maintenance (repair, reset...)")
        print("\n0. Quit")
        choice = user_choice()
        if choice == "1":
            run_red(autorestart=True)
        elif choice == "2":
            run_red(autorestart=False)
        elif choice == "3":
            update_menu()
        elif choice == "4":
            requirements_menu()
        elif choice == "5":
            maintenance_menu()
        elif choice == "0":
            break
        clear_screen()

if __name__ == '__main__':
    abspath = os.path.abspath(__file__)
    dirname = os.path.dirname(abspath)
    # Sets current directory to the script's
    os.chdir(dirname)
    if not PYTHON_OK:
        print("Red needs Python 3.5 or superior. Install the required "
              "version.\nPress enter to continue.")
        if INTERACTIVE_MODE:
            wait()
        exit(1)
    if pip is None:
        print("Red cannot work without the pip module. Please make sure to "
              "install Python without unchecking any option during the setup")
        wait()
        exit(1)
    if args.repair:
        reset_red(git_reset=True)
    if args.update_red:
        update_red()
    if args.update_reqs or args.update_reqs_no_audio:
        install_reqs(audio=False)
    if INTERACTIVE_MODE:
        main()
    elif args.start:
        print("Starting Red selfbot...")
        run_red(autorestart=args.auto_restart)
