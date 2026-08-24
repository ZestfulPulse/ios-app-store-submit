import 'package:permission_handler/permission_handler.dart';

Future<void> requestCamera() async {
  await Permission.camera.request();
}

void main() {}
