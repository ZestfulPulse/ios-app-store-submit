import 'package:flutter/material.dart';

class BigButton extends StatelessWidget {
  const BigButton({super.key});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      key: const Key('primaryActionButton'),
      child: GestureDetector(
        onTap: () {},
        child: const Icon(Icons.check),
      ),
    );
  }
}

void main() {}
