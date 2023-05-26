#!/usr/bin/env python3

from pprint import pprint
from datetime import date, datetime
from os import system
from pathlib import Path
import shutil
import json
from typing import List, Optional
import os
from dataclasses import dataclass
from traceback import format_exc
from typing_extensions import Self
from htmlmin import minify as html_minify

from frontmatter import load
from markdown import markdown as _markdown
from slugify import slugify
from jinja2 import Environment, FileSystemLoader, select_autoescape, BaseLoader
from docopt import docopt


LIB_DIR = os.path.split(__file__)[0]


@dataclass
class Tag:
    title: str
    slug: str
    url: str

    def __hash__(self):
        return hash((self.title, self.slug, self.url))
        return f'{self.title}-{self.slug}-{self.url}'


@dataclass
class Page:
    title: str
    author: str
    body: str
    dst: str
    description: str
    date: Optional[date]
    url: str
    template: str
    nolist: bool
    image: str
    tags: List[Tag]
    related: List[Self]

    def __hash__(self):
        return hash((self.title, self.dst, self.url))


def mkdir(path):
    return Path(path).mkdir(parents=True, exist_ok=True)


def mkdir_parent(path):
    return Path(path).parent.mkdir(parents=True, exist_ok=True)


def read(path):
    with open(path, 'r') as f:
        return f.read()


def write(path, data):
    with open(path, 'w') as f:
        return f.write(data)


def read_page(path):
    defaults = dict(
        title="",
        description="",
        date="2023-02-23",
        draft=False,
        tags=[],
        body="",
    )
    data = load(path)
    if data.content:
        data['body'] = data.content
    defaults.update(data)
    defaults['date'] = datetime.strptime(defaults['date'], "%Y-%m-%d")
    return defaults


SITEMAP_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="https://www.w3.org/1999/xhtml">	
	<url>
        <loc>{{url}}</loc>
        <lastmod>{{today.strftime("%Y-%m-%d")}}</lastmod>
	</url>
	{% for page in pages %}
	<url>
        <loc>{{page.url}}</loc>
        <lastmod>{{page.date.strftime("%Y-%m-%d")}}</lastmod>
	</url>
	{% endfor %}
	{% for tag in tags %}
	<url>
		<loc>{{tag.url}}</loc>
	</url>
	{% endfor %}
</urlset>""" # noqa


def markdown(text):
    return _markdown(
        text,
        extensions=[
            'fenced_code',
            'tables',
            'sane_lists',
            'markdown.extensions.toc',
        ],
    )


def merge_two_folders(root_src_dir, root_dst_dir):
    for src_dir, dirs, files in os.walk(root_src_dir):
        dst_dir = src_dir.replace(root_src_dir, root_dst_dir, 1)
        if not os.path.exists(dst_dir):
            os.makedirs(dst_dir)

        for file_ in files:
            src_file = os.path.join(src_dir, file_)
            dst_file = os.path.join(dst_dir, file_)
            if os.path.exists(dst_file):
                os.remove(dst_file)
            shutil.copy(src_file, dst_dir)


class Blog:
    def __init__(self, config, markdown=markdown):
        self.config = config
        self.markdown = markdown

        if not Path(self.config['theme']).is_dir() and not Path(f"{LIB_DIR}/{self.config['theme']}"):
            raise Exception("Could not find theme directory")
        elif Path(self.config['theme']).is_dir():
            # Precedence to local folder
            pass
        elif Path(f"{LIB_DIR}/{self.config['theme']}"):
            self.config['theme'] = f"{LIB_DIR}/{self.config['theme']}"

        self.title = self.config.get("title", "Tiger Blog Engine")
        self.description = self.config.get("description", "Welcome to the Awesome Tiger Blog Engine")
        self.type = self.config.get("type", "BlogPosting")
        self.keywords = self.config.get("keywords", "blogs developer frontend backend")
        self.name = self.config.get("name", "Tiger Blog Engine")

        self.logo = self.config.get("logo", "")
        self.favicon = self.config.get("favicon", "")
        self.sidebar_bg = self.config.get("sidebar_bg", "")

        self.tags = []
        self.env = Environment(
            loader=FileSystemLoader(["templates/", self.config['theme']]),
            autoescape=select_autoescape(),
        )

        self.files = [
            os.path.join(dp, f)
            for dp, dn, filenames in os.walk(self.config['content_path'])
            for f in filenames
        ]

        self.pages = []
        for fn in self.files:
            if not fn.endswith('.md'):
                continue

            page_data = read_page(fn)
            tags = []
            for tag in page_data['tags']:
                tags.append(Tag(
                    title=tag,
                    slug=f'tags/{slugify(tag)}',
                    url=f"{self.config['host']}/tags/{slugify(tag)}/"),
                )

            path = fn[len(self.config['content_path']):]

            if path.endswith("index.md"):
                # if path is of format /my-blog-post/index.md
                path = path[:-9]
            else:
                # if path is of format /my-blog-post.md
                path = path[0:-3]

            dst = self.config['tmp'] + path
            print(dst)
            if page_data['date'] and page_data['date'] > datetime.today():
                continue

            image = page_data.get("image", "")
            if image != '':
                # TODO: also make this image with my-blog-post.md
                post_path = fn[len(self.config['content_path']):].\
                    replace('index.md', '')
                image = f"{self.config['host']}/{post_path}/{image}"

            self.pages.append(Page(
                title=page_data['title'],
                tags=tags,
                description=page_data['description'],
                author=page_data.get('author', ''),
                date=page_data['date'],
                image=image,
                nolist=page_data.get('nolist', False),
                body=page_data['body'],
                template=page_data.get('template', "post.html"),
                dst=dst,
                url=f"{self.config['host']}{path}/",
                related=[],
            ))

    def prepare(self):
        print("Sorting pages..")
        self.pages = sorted(self.pages, key=lambda o: o.date, reverse=True)

        print("Organizing tags..")
        from collections import Counter
        for page in self.pages:
            # TODO maybe make this scored with amount of tags in common
            # But for now it is good and fast
            page.related = [
                p
                for p in self.pages
                # common tags > 0 (relevancy by tag amount)
                if len(Counter(page.tags) & Counter(p.tags)) > 0
                and p != page
            ]
            for tag in page.tags:
                self.tags.append(tag)

        self.tags = list(set(self.tags))

    def get_pages_with_tag(self, tag):
        return list(set([
            page
            for page
            in self.pages if tag.slug in [t.slug for t in page.tags]
        ]))

    def get_template(self, name):
        return self.env.get_template(name)

    def write_listing(self, path, pages, tag, url):
        pages = [page for page in pages if not page.nolist]
        mkdir_parent(path)
        context = dict(
            tag=tag,
            blog=self,
            pages=[p for p in pages],
            url=url,
            blog_url=f"{self.config['host']}/",
        )
        write(
            path,
            html_minify(self.get_template("listing.html").render(**context)),
        )

    def write_pages(self):
        print("Writing pages..")
        for page in self.pages:
            page.body_html = self.markdown(page.body)
            mkdir(page.dst)
            template = self.get_template(page.template)
            write(
                f'{page.dst}/index.html',
                html_minify(template.render(
                    blog=self,
                    page=page,
                    url=page.url,
                    blog_url=f"{self.config['host']}/",
                )),
            )

    def copy_files(self):
        print("Coyping files..")
        for file in self.files:
            if file.endswith(".md"):
                continue
            dst = self.config['tmp'] + file[len(self.config['content_path']):]
            print(dst)
            mkdir_parent(dst)
            shutil.copy2(file, dst)

    def write_sitemap(self, extra_sitemaps=[]):
        print("Writing sitemap..")
        pages = list(self.pages) + extra_sitemaps
        env = Environment(loader=BaseLoader())

        with open(f"{self.config['tmp']}/sitemap.xml", "w") as f:
            f.write(env.from_string(SITEMAP_TEMPLATE).render(
                blog=self,
                pages=pages,
                tags=self.tags,
                today=datetime.today(),
                blog_url=f"{self.config['host']}/",
                url=f"{self.config['host']}/",
            ))

    def save_custom_static_images(self, attrs: dict):
        for attr, default in attrs.items():
            file = getattr(self, attr)

            if not Path(file).is_file():
                setattr(self, attr, default)
                continue

            if not file.split(".")[-1] in ["png", "jpeg", "jpg", "ico", "svg"]:
                setattr(self, attr, default)
                continue

            filename = file.split("/")[-1]
            res_path = f"{self.config['tmp']}/static/images/{filename}"

            shutil.copy2(file, res_path)
            setattr(self, attr, f"static/images/{filename}")

    def prepare_static(self):
        print("Prepare static..")

        if Path(f'{self.config["theme"]}/static').is_dir():
            shutil.copytree(f'{self.config["theme"]}/static', f"{self.config['tmp']}/static")

        if Path("static").is_dir():
            merge_two_folders("static", f"{self.config['tmp']}/static")

        attrs_default = {
            "logo": "static/images/nav-logo.svg",
            "favicon": "static/images/favicon.ico",
            "sidebar_bg": "static/images/aside-logo.svg",
        }

        self.save_custom_static_images(attrs_default)

        print(f"favicon: '{self.favicon}'")
        print(f"logo: '{self.logo}'")
        print(f"sidebar_bg: '{self.sidebar_bg}'")


def main(config):
    # This have to be called after all pages
    # have been loaded in. If you have custom pages
    # please add them before blog.prepare
    blog = Blog(config)
    blog.prepare()

    shutil.rmtree(blog.config['tmp'], ignore_errors=True, onerror=None)
    mkdir(blog.config['tmp'])

    blog.prepare_static()
    blog.write_sitemap()
    blog.write_pages()
    blog.write_listing(
        f"{blog.config['tmp']}/index.html",
        blog.pages,
        None,
        f'{blog.config["host"]}/',
    )

    for tag in blog.tags:
        blog.write_listing(
            f"{blog.config['tmp']}/{tag.slug}/index.html",
            blog.get_pages_with_tag(tag),
            tag,
            tag.url,
        )

    blog.copy_files()

    shutil.rmtree(blog.config['output'], ignore_errors=True, onerror=None)
    shutil.copytree(blog.config['tmp'] + "/", blog.config['output'])


def build(config):
    try:
        # This is the default way of calling the blog engine
        # but you can make your own custom way
        if config:
            c = json.loads(read(config))
        else:
            c = json.loads(read(f"{LIB_DIR}/config.json"))

        main(c)

        print("Ok")
    except: # noqa
        print("Error happened when compiling")
        print(format_exc())


def print_it(config):
    try:
        # This is the default way of calling the blog engine
        # but you can make your own custom way
        if config:
            c = json.loads(read(config))
        else:
            c = json.loads(read("config.json"))

        blog = Blog(c)
        blog.prepare()
        for page in blog.pages:
            pprint(dict(
                title=page.title,
                author=page.author,
                body=page.body,
                dst=page.dst,
                description=page.description,
                date=page.date,
                url=page.url,
                template=page.template,
                nolist=page.nolist,
                image=page.image,
                tags=page.tags,
                related=page.related,
            ))

        print("Ok")
    except: # noqa
        print("Error happened when compiling")
        print(format_exc())



doc = """tigerblog

Usage:
  tigerblog.py build [--config=<config>] [--future]
  tigerblog.py serve
  tigerblog.py buildserve [--config=<config>] [--future]
  tigerblog.py print [--config=<config>]

Options:
  -h --help     Show this screen.
"""


def cli():
    arguments = docopt(doc, version='tigerblog.py 0.1')
    if arguments['build']:
        build(arguments['--config'])
    elif arguments['serve']:
        system("cd dist && python3 -m http.server -b localhost")
    elif arguments['buildserve']:
        build(arguments['--config'])
        system("cd dist && python3 -m http.server -b localhost")
    elif arguments['print']:
        print_it(arguments['--config'])


if __name__ == "__main__":
    cli()
