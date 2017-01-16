import datetime
import itertools
import pytz

from rest_framework import filters
from rest_framework.decorators import detail_route
from rest_framework.response import Response

from ESSArch_Core.WorkflowEngine.models import (
    ProcessStep,
    ProcessTask,
)

from preingest.serializers import (
    ProcessStepSerializer,
    ProcessStepChildrenSerializer,
    ProcessTaskSerializer,
    ProcessTaskDetailSerializer,
    GroupSerializer,
    GroupDetailSerializer,
    PermissionSerializer,
    UserSerializer,
)

from django.contrib.auth.models import User, Group, Permission
from rest_framework import viewsets


class UserViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows users to be viewed or edited.
    """
    queryset = User.objects.all().order_by('-date_joined')
    serializer_class = UserSerializer


class GroupViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows groups to be viewed or edited.
    """
    queryset = Group.objects.all()

    def get_serializer_class(self):
        if self.action == 'list':
            return GroupSerializer

        return GroupDetailSerializer


class PermissionViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows permissions to be viewed or edited.
    """
    queryset = Permission.objects.all()
    serializer_class = PermissionSerializer


class ProcessStepViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows steps to be viewed or edited.
    """
    queryset = ProcessStep.objects.all()
    serializer_class = ProcessStepSerializer

    @detail_route(methods=['get'], url_path='children')
    def children(self, request, pk=None):
        step = self.get_object()
        child_steps = step.child_steps.all()
        tasks = step.tasks.all()
        queryset = sorted(
            itertools.chain(child_steps, tasks),
            key=lambda instance: instance.time_started or
            datetime.datetime(datetime.MAXYEAR, 1, 1, 1, 1, 1, 1, pytz.UTC)
        )
        page = self.paginate_queryset(queryset)

        if page is not None:
            serializers = ProcessStepChildrenSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializers.data)
        serializers = ProcessStepChildrenSerializer(queryset, many=True, context={'request': request})
        return Response(serializers.data)

    @detail_route(methods=['get'], url_path='child-steps')
    def child_steps(self, request, pk=None):
        step = self.get_object()
        child_steps = step.child_steps.all()
        page = self.paginate_queryset(child_steps)
        if page is not None:
            serializers = ProcessStepSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializers.data)
        serializers = ProcessStepSerializer(child_steps, many=True, context={'request': request})
        return Response(serializers.data)

    @detail_route(methods=['get'])
    def tasks(self, request, pk=None):
        step = self.get_object()
        tasks = step.tasks.all()
        page = self.paginate_queryset(tasks)
        if page is not None:
            serializers = ProcessTaskSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializers.data)
        serializers = ProcessTaskSerializer(tasks, many=True, context={'request': request})
        return Response(serializers.data)

    @detail_route(methods=['post'])
    def run(self, request, pk=None):
        self.get_object().run()
        return Response({'status': 'running step'})

    @detail_route(methods=['post'])
    def undo(self, request, pk=None):
        self.get_object().undo()
        return Response({'status': 'undoing step'})

    @detail_route(methods=['post'], url_path='undo-failed')
    def undo_failed(self, request, pk=None):
        self.get_object().undo(only_failed=True)
        return Response({'status': 'undoing failed tasks in step'})

    @detail_route(methods=['post'])
    def retry(self, request, pk=None):
        self.get_object().retry()
        return Response({'status': 'retrying step'})

    @detail_route(methods=['post'])
    def resume(self, request, pk=None):
        self.get_object().resume()
        return Response({'status': 'resuming step'})


class ProcessTaskViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows tasks to be viewed or edited.
    """
    queryset = ProcessTask.objects.all()
    serializer_class = ProcessTaskSerializer

    def get_serializer_class(self):
        if self.action == 'list':
            return ProcessTaskSerializer

        return ProcessTaskDetailSerializer

    @detail_route(methods=['post'])
    def undo(self, request, pk=None):
        self.get_object().undo()
        return Response({'status': 'undoing task'})

    @detail_route(methods=['post'])
    def retry(self, request, pk=None):
        self.get_object().retry()
        return Response({'status': 'retries task'})
