import fire

from .importer import load_elections_data

if __name__ == "__main__":
    fire.Fire(load_elections_data)
