run:
	uvicorn app.api:app --reload

lint:
	flake8 app
	isort --check --diff app
	black --check app

format:
	isort app tests
	black app tests

test:
	pytest -sv tests
