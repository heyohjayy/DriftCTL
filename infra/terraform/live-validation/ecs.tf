data "aws_iam_policy_document" "ecs_tasks_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_ecs_cluster" "fargate" {
  count = var.enable_ecs_fargate_validation ? 1 : 0

  name = "${var.validation_prefix}-ecs"

  setting {
    name  = "containerInsights"
    value = "disabled"
  }

  tags = merge(local.common_tags, {
    Name = "${var.validation_prefix}-ecs"
  })
}

resource "aws_iam_role" "ecs_execution" {
  count = var.enable_ecs_fargate_validation ? 1 : 0

  name               = "${var.validation_prefix}-ecs-execution-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume_role.json

  tags = merge(local.common_tags, {
    Name = "${var.validation_prefix}-ecs-execution-role"
  })
}

resource "aws_iam_role_policy_attachment" "ecs_execution" {
  count = var.enable_ecs_fargate_validation ? 1 : 0

  role       = aws_iam_role.ecs_execution[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role" "ecs_task" {
  count = var.enable_ecs_fargate_validation ? 1 : 0

  name               = "${var.validation_prefix}-ecs-task-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume_role.json

  tags = merge(local.common_tags, {
    Name = "${var.validation_prefix}-ecs-task-role"
  })
}

resource "aws_cloudwatch_log_group" "ecs" {
  count = var.enable_ecs_fargate_validation ? 1 : 0

  name              = "/driftctl/${var.validation_prefix}/ecs"
  retention_in_days = 7

  tags = merge(local.common_tags, {
    Name = "${var.validation_prefix}-ecs-logs"
  })
}

resource "aws_security_group" "ecs_task" {
  count = var.enable_ecs_fargate_validation ? 1 : 0

  name        = "${var.validation_prefix}-ecs-task-sg"
  description = "No-inbound security group for the optional DriftCTL ECS Fargate validation task"
  vpc_id      = aws_vpc.validation.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, {
    Name = "${var.validation_prefix}-ecs-task-sg"
  })
}

resource "aws_ecs_task_definition" "fargate" {
  count = var.enable_ecs_fargate_validation ? 1 : 0

  family                   = "${var.validation_prefix}-fargate"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.ecs_execution[0].arn
  task_role_arn            = aws_iam_role.ecs_task[0].arn

  container_definitions = jsonencode([
    {
      name      = "web"
      image     = "public.ecr.aws/docker/library/nginx:1.27"
      essential = true
      portMappings = [
        {
          containerPort = 80
          hostPort      = 80
          protocol      = "tcp"
        }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.ecs[0].name
          awslogs-region        = var.aws_region
          awslogs-stream-prefix = "ecs"
        }
      }
    }
  ])

  tags = merge(local.common_tags, {
    Name = "${var.validation_prefix}-fargate"
  })
}

resource "aws_ecs_service" "fargate" {
  count = var.enable_ecs_fargate_validation ? 1 : 0

  name                   = "${var.validation_prefix}-fargate"
  cluster                = aws_ecs_cluster.fargate[0].id
  task_definition        = aws_ecs_task_definition.fargate[0].arn
  desired_count          = var.ecs_desired_count
  launch_type            = "FARGATE"
  enable_execute_command = false

  network_configuration {
    assign_public_ip = true
    security_groups  = [aws_security_group.ecs_task[0].id]
    subnets = [
      aws_subnet.public_primary.id,
      aws_subnet.public_secondary.id,
    ]
  }

  tags = merge(local.common_tags, {
    Name = "${var.validation_prefix}-fargate"
  })

  depends_on = [
    aws_iam_role_policy_attachment.ecs_execution,
    aws_cloudwatch_log_group.ecs,
  ]
}
