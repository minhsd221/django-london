import os
import tempfile
from _decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APIClient

from core.models import Recipe, Tag, Ingredient

from recipe.serializers import (
    RecipeSerializer,
    RecipeDetailSerializer,
)

from PIL import Image

RECIPES_URL = reverse('recipe:recipe-list')


def detail_url(recipe_id):
    return reverse('recipe:recipe-detail', args=[recipe_id])


def image_upload_url(recipe_id):
    return reverse('recipe:recipe-upload-image', args=[recipe_id])


def create_recipe(user, **param):
    defaults = {
        'title': 'Sample recipe title',
        'time_minutes': 22,
        'price': Decimal('5.25'),
        'description': 'Sample',
        'link': 'http ff'
    }
    defaults.update(param)

    recipe = Recipe.objects.create(user=user, **defaults)
    return recipe


def create_user(**params):
    return get_user_model().objects.create_user(**params)


class PublicRecipeAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_auth_required(self):
        res = self.client.get(RECIPES_URL)
        self.assertEquals(res.status_code, status.HTTP_401_UNAUTHORIZED)


class PrivateRecipeApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = create_user(email='user@example.com', password='testpass123')
        self.client.force_authenticate(self.user)

    def test_retrieve_recipes(self):
        create_recipe(user=self.user)
        create_recipe(user=self.user)

        res = self.client.get(RECIPES_URL)

        recipes = Recipe.objects.all().order_by('-id')
        serializer = RecipeSerializer(recipes, many=True)
        self.assertEquals(res.status_code, status.HTTP_200_OK)
        self.assertEquals(res.data, serializer.data)

    def test_recipe_list_limited_to_user(self):
        other_user = create_user(email='other@example.com', password='password123')

        create_recipe(user=other_user)
        create_recipe(user=self.user)

        res = self.client.get(RECIPES_URL)

        recipes = Recipe.objects.filter(user=self.user)
        serializer = RecipeSerializer(recipes, many=True)
        self.assertEquals(res.status_code, status.HTTP_200_OK)
        self.assertEquals(res.data, serializer.data)

    def test_get_recipe_detail(self):
        recipe = create_recipe(user=self.user)
        url = detail_url(recipe.id)
        res = self.client.get(url)

        serializer = RecipeDetailSerializer(recipe)
        self.assertEquals(res.data, serializer.data)

    def test_create_recipe(self):
        payload = {
            'title': 'Sample recipe',
            'time_minutes': 30,
            'price': Decimal('5.99')
        }
        res = self.client.post(RECIPES_URL, payload)
        # print(res.data)
        self.assertEquals(res.status_code, status.HTTP_201_CREATED)

        recipe = Recipe.objects.get(id=res.data['id'])
        serializer = RecipeDetailSerializer(recipe)

        # for k, v in payload.items():
        #     print(k, v)
        #     self.assertEquals(getattr(recipe, k), v)

        self.assertEquals(serializer.data, res.data)

    def test_partial_update(self):
        original_link = 'https://example.com/recipe.pdf'
        recipe = create_recipe(
            user=self.user,
            title='Sample recipe title',
            link=original_link
        )

        payload = {
            'title': 'New recipe title'
        }
        url = detail_url(recipe.id)
        res = self.client.patch(url, payload)

        self.assertEquals(res.status_code, status.HTTP_200_OK)
        recipe.refresh_from_db()
        self.assertEquals(recipe.title, payload['title'])
        self.assertEquals(recipe.link, original_link)
        self.assertEquals(recipe.user, self.user)

    def test_full_update(self):
        recipe = create_recipe(
            user=self.user,
            title='Sample recipe title',
            link='ff',
            description='Des'
        )

        payload = {
            'title': 'New recipe title',
            'link': 'new ff',
            'description': 'New recipe des',
            'time_minutes': 10,
            'price': Decimal('2.5'),

        }

        url = detail_url(recipe.id)
        res = self.client.put(url, payload)

        self.assertEquals(res.status_code, status.HTTP_200_OK)
        recipe.refresh_from_db()
        self.assertEquals(recipe.user, self.user)

        serializer = RecipeDetailSerializer(recipe)
        self.assertEquals(serializer.data, res.data)

    def test_update_user_returns_error(self):
        new_user = create_user(email='ff@ff.com', password='1')
        recipe = create_recipe(user=self.user)

        payload = {
            'user': new_user.id
        }
        url = detail_url(recipe.id)
        # print("Recipe user:", recipe.user)
        res = self.client.patch(url, payload)  # user won't patch because of serializer
        # print("res:", res.data)
        # print("res:", res.status_code)

        recipe.refresh_from_db()

        # print("Recipe user 2:", recipe.user)
        self.assertEquals(recipe.user, self.user)

    def test_delete_recipe(self):
        recipe = create_recipe(user=self.user)

        url = detail_url(recipe.id)
        res = self.client.delete(url)

        self.assertEquals(res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Recipe.objects.filter(id=recipe.id).exists())

    def test_delete_other_users_recipe_error(self):
        new_user = create_user(email='user2@example.com', password='test123')
        recipe = create_recipe(user=new_user)

        url = detail_url(recipe.id)
        res = self.client.delete(url)

        self.assertEquals(res.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Recipe.objects.filter(id=recipe.id).exists())

        # self.assertEquals(res.status_code, status.HTTP_204_NO_CONTENT)
        # self.assertFalse(Recipe.objects.filter(id=recipe.id).exists())

    def test_create_recipe_with_new_tags(self):
        payload = {
            'title': 'Thai Prawn Curry',
            'time_minutes': 30,
            'price': Decimal('2.5'),
            'tags': [{'name': 'Thai'}, {'name': 'Dinner'}]
        }
        res = self.client.post(RECIPES_URL, payload, format='json')

        self.assertEquals(res.status_code, status.HTTP_201_CREATED)
        recipes = Recipe.objects.filter(user=self.user)
        self.assertEquals(recipes.count(), 1)

        recipe = recipes[0]
        self.assertEquals(recipe.tags.count(), 2)
        for tag in payload['tags']:
            exists = recipe.tags.filter(
                name=tag['name'],
                user=self.user,
            )
            self.assertTrue(exists)

    def test_create_recipe_with_existing_tags(self):
        tag_indian = Tag.objects.create(user=self.user, name='Indian')
        payload = {
            'title': 'Pongal',
            'time_minutes': 60,
            'price': Decimal('4.5'),
            'tags': [{'name': 'Indian'}, {'name': 'Breakfast'}]
        }

        res = self.client.post(RECIPES_URL, payload, format='json')

        self.assertEquals(res.status_code, status.HTTP_201_CREATED)
        recipes = Recipe.objects.filter(user=self.user)
        self.assertEquals(recipes.count(), 1)
        recipe = recipes[0]
        self.assertEquals(recipe.tags.count(), 2)
        self.assertIn(tag_indian, recipe.tags.all())

        for tag in payload['tags']:
            exists = recipe.tags.filter(
                name=tag['name'],
                user=self.user
            ).exists()
            self.assertTrue(exists)

    def test_create_tag_on_update(self):
        recipe = create_recipe(user=self.user)
        payload = {
            'tags': [{'name': 'Lunch'}]
        }

        url = detail_url(recipe.id)
        res = self.client.patch(url, payload, format='json')

        self.assertEquals(res.status_code, status.HTTP_200_OK)
        new_tag = Tag.objects.get(user=self.user, name='Lunch')
        self.assertIn(new_tag, recipe.tags.all())

    def test_update_recipe_assign_tag(self):
        tag_breakfast = Tag.objects.create(user=self.user, name='Breakfast')
        recipe = create_recipe(user=self.user)
        recipe.tags.add(tag_breakfast)

        tag_lunch = Tag.objects.create(user=self.user, name='Lunch')
        payload = {
            'tags': [{
                'name': 'Lunch'
            }]
        }
        url = detail_url(recipe.id)
        res = self.client.patch(url, payload, format='json')
        self.assertEquals(res.status_code, status.HTTP_200_OK)
        self.assertIn(tag_lunch, recipe.tags.all())
        self.assertNotIn(tag_breakfast, recipe.tags.all())

    def test_clear_recipe_tags(self):
        tag = Tag.objects.create(user=self.user, name='Dessert')
        recipe = create_recipe(user=self.user)
        recipe.tags.add(tag)

        payload = {
            'tags': []
        }
        url = detail_url(recipe.id)
        res = self.client.patch(url, payload, format='json')
        self.assertEquals(res.status_code, status.HTTP_200_OK)
        self.assertEquals(recipe.tags.count(), 0)

    def test_create_recipe_with_new_ingredients(self):
        payload = {
            'title': 'Thai Prawn Curry',
            'time_minutes': 30,
            'price': Decimal('2.5'),
            'ingredients': [{'name': 'Cauli'}, {'name': 'Salt'}]
        }
        res = self.client.post(RECIPES_URL, payload, format='json')

        self.assertEquals(res.status_code, status.HTTP_201_CREATED)
        recipes = Recipe.objects.filter(user=self.user)
        self.assertEquals(recipes.count(), 1)

        recipe = recipes[0]
        self.assertEquals(recipe.ingredients.count(), 2)
        for ingredient in payload['ingredients']:
            exists = recipe.ingredients.filter(
                name=ingredient['name'],
                user=self.user,
            )
            self.assertTrue(exists)

    def test_create_recipe_with_existing_ingredients(self):
        ingredient = Ingredient.objects.create(user=self.user, name='Lemon')
        payload = {
            'title': 'Soup',
            'time_minutes': 60,
            'price': Decimal('4.5'),
            'ingredients': [{'name': 'Lemon'}, {'name': 'Fish Sauce'}]
        }

        res = self.client.post(RECIPES_URL, payload, format='json')

        self.assertEquals(res.status_code, status.HTTP_201_CREATED)
        recipes = Recipe.objects.filter(user=self.user)
        self.assertEquals(recipes.count(), 1)
        recipe = recipes[0]
        self.assertEquals(recipe.ingredients.count(), 2)
        self.assertIn(ingredient, recipe.ingredients.all())

        for ingredient in payload['ingredients']:
            exists = recipe.ingredients.filter(
                name=ingredient['name'],
                user=self.user
            ).exists()
            self.assertTrue(exists)

    def test_create_ingredient_on_update(self):
        recipe = create_recipe(user=self.user)
        payload = {
            'ingredients': [{'name': 'Limes'}]
        }

        url = detail_url(recipe.id)
        res = self.client.patch(url, payload, format='json')

        self.assertEquals(res.status_code, status.HTTP_200_OK)
        new_ingredient = Ingredient.objects.get(user=self.user, name='Limes')
        self.assertIn(new_ingredient, recipe.ingredients.all())

    def test_update_recipe_assign_ingredient(self):
        ingredient1 = Ingredient.objects.create(user=self.user, name='Pepper')
        recipe = create_recipe(user=self.user)
        recipe.ingredients.add(ingredient1)

        ingredient2 = Ingredient.objects.create(user=self.user, name='Chili')
        payload = {
            'ingredients': [{
                'name': 'Chili'
            }]
        }
        url = detail_url(recipe.id)
        res = self.client.patch(url, payload, format='json')
        self.assertEquals(res.status_code, status.HTTP_200_OK)
        self.assertIn(ingredient2, recipe.ingredients.all())
        self.assertNotIn(ingredient1, recipe.ingredients.all())

    def test_clear_recipe_ingredients(self):
        ingredient = Ingredient.objects.create(user=self.user, name='Garlic')
        recipe = create_recipe(user=self.user)
        recipe.ingredients.add(ingredient)

        payload = {
            'ingredients': []
        }
        url = detail_url(recipe.id)
        res = self.client.patch(url, payload, format='json')
        self.assertEquals(res.status_code, status.HTTP_200_OK)
        self.assertEquals(recipe.ingredients.count(), 0)


    class ImageUploadTests(TestCase):
        def setUp(self):
            self.client = APIClient()
            self.user = get_user_model().objects.create_user(
                'user@example.com',
                'password123'
            )
            self.client.force_authenticate(self.user)
            self.recipe = create_recipe(user=self.user)

        def tearDown(self):
            self.recipe.image.delete()

        def test_upload_image(self):
            """Test uploading an image to a recipe."""
            url = image_upload_url(self.recipe.id)
            with tempfile.NamedTemporaryFile(suffix='.jpg') as image_file:
                img = Image.new('RGB', (10, 10))
                img.save(image_file, format='JPEG')
                image_file.seek(0)
                payload = {'image': image_file}
                res = self.client.post(url, payload, format='multipart')

            self.recipe.refresh_from_db()
            self.assertEqual(res.status_code, status.HTTP_200_OK)
            self.assertIn('image', res.data)
            self.assertTrue(os.path.exists(self.recipe.image.path))

        def test_upload_bad_request(self):
            url = image_upload_url(self.recipe.id)
            payload = {
                'image': 'not an image'
            }
            res = self.client.post(url, payload, format='multipart')

            self.assertEquals(res.status_code, status.HTTP_400_BAD_REQUEST)


