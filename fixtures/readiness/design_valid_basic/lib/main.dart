import 'package:flutter/material.dart';

class HomePage extends StatelessWidget {
  const HomePage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Column(
          children: [
            IconButton(
              tooltip: 'Close',
              icon: const Icon(Icons.close),
              onPressed: () {},
            ),
            ElevatedButton(
              onPressed: () {},
              child: Text(AppLocalizations.of(context)!.continueLabel),
            ),
          ],
        ),
      ),
    );
  }
}

void main() {}
