import sys
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
import requests
import os
from shutil import rmtree
import string
import random
import json
import re


class Crawler:
    MAX_DEPTH = 5
    IMAGES_FOLDER_NAME = 'images'
    SUPPORTED_IMAGE_TYPES = ['jpg', 'jpeg', 'bmp', 'png', 'ico', 'webp', 'jpeg', 'gif', 'tiff']
    base_url = ''
    crawl_depth = 1
    unprocessed_urls = {}
    processed_urls = {}
    crawl_index = {}
    logger = []
    debug_mode = True

    def crawl_main(self):
        result_status, result = self.get_parameters_and_validate(sys.argv)
        if not result_status:
            print(f'Cannot continue, {result}')
            return
        self.unprocessed_urls[self.base_url] = 1
        result_status, result = self.create_images_folder()
        if not result_status:
            print(f'Cannot continue, problem creating {self.IMAGES_FOLDER_NAME} directory, error is {result}')
            return
        self.process_all_url_links()
        self.download_images()
        downloaded_images_counter = self.save_json_file()
        if len(self.logger) > 0:
            print(f'\nProcess completed, {downloaded_images_counter} images were downloaded. Following issues found:')
            print('\n'.join(self.logger))
        else:
            print(f'\nProcess completed successfully. {downloaded_images_counter} images were downloaded.')

    def get_parameters_and_validate(self, args):
        """
        get command line parameters and validate that all is ok
        """
        # check number of arguments
        if len(args) < 3:
            return False, 'Wrong number of parameters provided, use crawl <start_url> <depth>'
        self.base_url = args[1].strip('/')
        check_url_result = self.check_url(self.base_url)
        if not check_url_result:
            return False, 'Wrong url provided'
        # confirm second parameter is a number
        try:
            self.crawl_depth = int(args[2])
        except ValueError:
            return False, 'Wrong depth value provided, use integer only'
        if self.crawl_depth > self.MAX_DEPTH:
            return False, f'Wrong depth value provided, maximum depth is {self.MAX_DEPTH}'

        return True, None

    @staticmethod
    def check_url(url):
        """
        check that given URL is valid
        """
        try:
            check_url_result = urlparse(url)
        except:
            return False
        return all([check_url_result.scheme, check_url_result.netloc])

    def create_images_folder(self):
        """
        delete images folder (if exists) and recreate it
        """
        try:
            rmtree(self.IMAGES_FOLDER_NAME)
        except FileNotFoundError:
            pass
        try:
            # folder_name = input("Enter Folder Name: ")
            os.mkdir(self.IMAGES_FOLDER_NAME)
            return True, None
        except Exception as e:
            return False, str(e)

    def process_all_url_links(self):
        """
        main loop for accessing all links on all levels
        """
        while len(self.unprocessed_urls) > 0:
            current_url_path = list(self.unprocessed_urls)[0]
            current_depth = self.unprocessed_urls[current_url_path]
            try:
                request = requests.get(current_url_path)
            except ConnectionError:
                self.log_errors(f'Error fetching page content, timeout occurred. page is {current_url_path}')
                self.mark_as_processed(current_depth, current_url_path)
                continue
            except Exception as e:
                self.log_errors(f'Error fetching page content. Exception is {e.__class__.__name__}: {str(e)}. '
                                f'page is {current_url_path}')
                self.mark_as_processed(current_depth, current_url_path)
                continue
            soup = BeautifulSoup(request.text, 'html.parser')
            # get next level links if we're not yet on the last required depth
            if current_depth < self.crawl_depth:
                self.get_all_url_links(soup, current_depth + 1)
            self.get_all_url_images(soup, current_url_path, current_depth)
            self.mark_as_processed(current_depth, current_url_path)
            if self.debug_mode:
                print(f'Unprocessed: {len(self.unprocessed_urls)}, processed: {len(self.processed_urls)}')

    def mark_as_processed(self, current_depth, current_url_path):
        # done with current link. move page to the processed list
        self.processed_urls[current_url_path] = current_depth
        del self.unprocessed_urls[current_url_path]

    def get_all_url_links(self, soup, cur_depth):
        """
        for a given page, get list of all links which are specified in the page
        """
        for a_ref in soup.find_all('a'):
            link = a_ref.get('href')
            if self.check_url(link) and not self.unprocessed_urls.get(link) and not self.processed_urls.get(link):
                self.unprocessed_urls[link] = cur_depth

    def add_to_crawl_index(self, image_link, parent_url, cur_depth):
        try:
            _ = self.crawl_index[(image_link, parent_url)]
            # image exists, do nothing
            return
        except KeyError:
            self.crawl_index[(image_link, parent_url)] = {'depth': cur_depth, 'download': False}

    def is_an_image_link(self, image_link):
        if image_link and image_link.split('.')[-1].lower() in self.SUPPORTED_IMAGE_TYPES:
            return True
        return False

    def get_all_url_images(self, soup, parent_url, cur_depth):
        self.get_img_tag_images(soup, parent_url, cur_depth)
        self.get_link_tag_images(soup, parent_url, cur_depth)
        self.get_explicit_link_images(str(soup), parent_url, cur_depth)

    def get_img_tag_images(self, soup, parent_url, cur_depth):
        """
        for a given page, get list of all images which include 'img' HTML tag in the page
        """
        for image in soup.find_all('img'):
            try:
                image_link = image["data-srcset"]
            except:
                try:
                    image_link = image["data-src"]
                except:
                    try:
                        image_link = image["data-fallback-src"]
                    except:
                        try:
                            image_link = image["src"]
                        except:
                            image_link = None
            if self.is_an_image_link(image_link):
                self.add_to_crawl_index(image_link, parent_url, cur_depth)

    def get_link_tag_images(self, soup, parent_url, cur_depth):
        """
        for a given page, get list of all images which include 'link' HTML tag in the page
        """
        for image in soup.find_all('link'):
            image_link = ''
            try:
                image_link = image.attrs.get('href')
                if self.is_an_image_link(image_link):
                    self.add_to_crawl_index(image_link, parent_url, cur_depth)
            except Exception as e:
                self.log_errors(f'Error fetching image path. Exception is {e.__class__.__name__}: {str(e)}. '
                                f'image link is {image_link}')

    def get_explicit_link_images(self, text, parent_url, cur_depth):
        # Regular expression pattern to match URLs in the given string
        img_url_pattern = re.compile(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+',
                                 re.IGNORECASE)

        # Find all matches in the text
        matched_urls = img_url_pattern.findall(text)
        for image_link in matched_urls:
            if self.is_an_image_link(image_link):
                self.add_to_crawl_index(image_link, parent_url, cur_depth)

    def download_images(self):
        """
        download all images that were found by the crawler
        """
        i = 1
        for image_key, image_info in self.crawl_index.items():
            if self.debug_mode:
                print(f'Downloading image {i} out of {len(self.crawl_index)}')
                i += 1
            image_path = image_key[0]
            try:
                image_name = image_path.split('/')[-1]
            except (AttributeError, ValueError) as e:
                self.log_errors(f'Error fetching image name. error is: {str(e)}. image link is {image_path}')
                continue
            image_path = urljoin(image_key[1], image_path)
            try:
                image = requests.get(image_path).content
                try:
                    # possibility of decode
                    image = str(image, 'utf-8')
                    if self.debug_mode:
                        self.log_errors(f'Error saving image. Either link is not an image or image not found. Output '
                                        f'is: {image}, image link is {image_path}')
                    else:
                        self.log_errors(f'Error saving image. Either link is not an image or image not found. Image '
                                        f'link is {image_path}')
                except UnicodeDecodeError:
                    image_path_for_save = self.get_image_path_for_save(image_name)
                    try:
                        with open(image_path_for_save, 'wb+') as f:
                            f.write(image)
                        self.crawl_index[image_key]['download'] = True
                    except FileNotFoundError as e:
                        self.log_errors(f'Error saving image. error is: {str(e)}. Image link is {image_path_for_save}')
            except Exception as e:
                self.log_errors(f'Error fetching image content. Exception is {e.__class__.__name__}: {str(e)}. '
                                f'image is {image_path}')

    def get_image_path_for_save(self, image_name):
        """
        get path for the image to be saved
        """
        image_path_for_save = f'{self.IMAGES_FOLDER_NAME}/{image_name}'
        if os.path.exists(image_path_for_save):
            # file already exists, create unique name
            letters = string.ascii_lowercase
            unique_file_name = f"{''.join(random.choice(letters) for i in range(5))}-{image_name}"
            image_path_for_save = f'{self.IMAGES_FOLDER_NAME}/{unique_file_name}'

        return image_path_for_save

    def save_json_file(self):
        image_list = []
        for image_key, image_info in self.crawl_index.items():
            if image_info['download']:
                image_list.append({'url': image_key[0], 'page': image_key[1], 'depth': image_info['depth']})
        json_index = json.dumps({'images': image_list})
        json_file = open(f'{self.IMAGES_FOLDER_NAME}/index.json', "w")
        json_file.write(json_index)
        json_file.close()
        return len(image_list)

    def log_errors(self, error_message):
        self.logger.append(error_message)


crawler = Crawler()
crawler.crawl_main()
