import concurrent.futures
import json
import urllib.request
from concurrent.futures._base import Future
from contextlib import suppress
from typing import Any, Dict, List

import graphql

API_DIRECTORY_URL = "https://raw.githubusercontent.com/APIs-guru/graphql-apis/master/apis.json"
FETCH_TIMEOUT = 30
CORPUS_PATH = "test/corpus-api-guru-catalog.json"
INTROSPECTION_QUERY = graphql.get_introspection_query()
INTROSPECTION_QUERY_PAYLOAD = json.dumps({"query": INTROSPECTION_QUERY}).encode("utf8")
INVALID_API_URLS = {"Deutsche Bahn": "https://bahnql.herokuapp.com/graphql"}
ADDITIONAL_APIS = {
    "AniList": "https://graphql.anilist.co/",
    "Artsy": "https://metaphysics-production.artsy.net/",
    "Contentful": "https://graphql.contentful.com/content/v1/spaces/f8bqpb154z8p/environments/master"
    "?access_token=9d5de88248563ebc0d2ad688d0473f56fcd31c600e419d6c8962f6aed0150599",
    "Countries v2": "https://countries-274616.ew.r.appspot.com/",
    "EtMDB": "https://etmdb.com/graphql",
    "Gitlab": "https://gitlab.com/api/graphql",
    "GraphQL Jobs": "https://api.graphql.jobs/",
    "React Finland": "https://api.react-finland.fi/graphql",
    "Universe": "https://www.universe.com/graphql",
    "TravelgateX": "https://api.travelgatex.com/",
    "Barcelona Urban Mobility API": "https://barcelona-urban-mobility-graphql-api.netlify.app/graphql",
    "TMDB": "https://tmdb.apps.quintero.io/",
    "SWAPI": "https://swapi-graphql.netlify.app/.netlify/functions/index",
    "Spotify": "https://spotify-api-graphql-console.herokuapp.com/graphql",
    "Spacex Land": "https://api.spacex.land/graphql",
    "PokeAPI": "https://pokeapi-graphiql.herokuapp.com/",
    "MusicBrainz": "https://graphbrainz.herokuapp.com/",
    "Ghibliql": "https://ghibliql.herokuapp.com/",
    "Câmara dos deputados Brasil": "https://graphql-camara-deputados.herokuapp.com/",
    "Weather API": "https://graphql-weather-api.herokuapp.com/",
    "UN SDG data series API": "http://linkedsdg.apps.officialstatistics.org/graphql/linkedsdg.apps.officialstatistics.org/graphql",
    "The Rick and Morty API": "https://rickandmortyapi.com/graphql",
    "Google directions API": "https://directions-graphql.herokuapp.com/graphql",
    "Spotify GraphQL Server": "https://spotify-graphql-server.herokuapp.com/graphql",
    "Planets": "https://pristine-gadget-267405.appspot.com/graphql/",
    "MongoDB Northwind demo": "https://graphql-compose.herokuapp.com/northwind/",
}


def load_json(url: str) -> Any:
    with urllib.request.urlopen(url) as response:
        return json.load(response)


def load_schema(url: str) -> str:
    request = urllib.request.Request(
        url,
        data=INTROSPECTION_QUERY_PAYLOAD,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request) as response:
        data = json.load(response)
    return introspection_result_to_sdl(data["data"])


def introspection_result_to_sdl(data: Dict[str, Any]) -> str:
    client_schema = graphql.build_client_schema(data)
    return graphql.print_schema(client_schema).strip()


def load_corpus(path: str = CORPUS_PATH) -> Dict[str, Any]:
    try:
        with open(path) as fd:
            return json.load(fd)
    except FileNotFoundError:
        return {}


def store_corpus(data: Dict[str, Any], path: str = CORPUS_PATH) -> None:
    with open(path, mode="w") as fd:
        json.dump(data, fd, indent=4, sort_keys=True)


def update_corpus(futures: List[Future], corpus_path: str = CORPUS_PATH) -> Dict[str, Any]:
    corpus = load_corpus(corpus_path)
    with suppress(concurrent.futures.TimeoutError):
        for future in concurrent.futures.as_completed(futures, timeout=FETCH_TIMEOUT):
            try:
                schema = future.result()
                corpus[future.name] = schema
            except Exception as exc:
                print(f"Error: {future.name} {exc}")
    return corpus


def main(directory_url: str = API_DIRECTORY_URL, corpus_path: str = CORPUS_PATH):
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = []

        def submit_future(_name, _url):
            future = executor.submit(load_schema, _url)
            future.name = _name
            futures.append(future)

        for api in load_json(directory_url):
            name = api["info"]["title"]
            if name in INVALID_API_URLS:
                url = INVALID_API_URLS[name]
            else:
                url = api["url"]

            submit_future(name, url)
        for name, url in ADDITIONAL_APIS.items():
            submit_future(name, url)

        corpus = update_corpus(futures, corpus_path)

    store_corpus(corpus, corpus_path)


if __name__ == "__main__":
    main()
