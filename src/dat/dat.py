from sys import argv

def main():
    print("This is Dat.")
    print("Arguments:", argv)
    command = get_function_by_name(argv[1])
    command()


def get_function_by_name(name):
    return globals()[name]


def commit():
    print("Committing changes")


if __name__ == "__main__":
    main()
